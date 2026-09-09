"""
Reusable colour helpers for Lightkey patchers.

Implements the patterns documented in docs/patterns.md §10–§13:

  * Anchor + variation palettes (uniform brightness)
  * Per-zone full-palette sweep
  * Sequence step builder with per-fixture intensity overrides

Copy this file into your working directory alongside resolve.py, then import:

    from colour_helpers import (
        pack_color, make_colour_var, fp_palette_uniform_brightness,
        fp_step, COLOUR_BANK,
    )

Most builders only need to override `FIX_UUID` (the fixture short-name → UUID
map) and ZONE lists at the top of their own script, then call these helpers.
"""

import math
import plistlib


def pack_color(r16, g16, b16, a16=0):
    """Pack four 16-bit channels into Lightkey's 64-bit colour integer.

    Byte order is **B low, G mid, R high, A top** — verified against Lightkey's
    own colour picker. An earlier revision of this file had R low, which made
    every red preset render BLUE on a real rig. Do not "fix" this back.

    Always wrapped in a 1-list when stored: `'color': [pack_color(...)]`.
    """
    return ((b16 & 0xFFFF) | ((g16 & 0xFFFF) << 16) |
            ((r16 & 0xFFFF) << 32) | ((a16 & 0xFFFF) << 48))


def c8(r, g, b):
    """8-bit RGB convenience wrapper: c8(255, 0, 0) -> packed red."""
    return pack_color(r * 257, g * 257, b * 257)


def unpack_rgb8(packed):
    """Inverse of c8 — use in validators to assert what a preset really renders."""
    return (((packed >> 32) & 0xFFFF) >> 8,
            ((packed >> 16) & 0xFFFF) >> 8,
            (packed & 0xFFFF) >> 8)


# ---------------------------------------------------------------------------
# Uniform-brightness colour bank — anchor + variation.
# Each palette is ((anchor_R, anchor_G, anchor_B), (var_R, var_G, var_B)).
# The anchor's dominant channel must be 0xFFFF and its variation MUST be 0 on
# that channel so brightness stays uniform across fixtures.
# ---------------------------------------------------------------------------

COLOUR_BANK = {
    # Warm
    'Fire Red':       ((0xFFFF, 0x0500, 0x0500), (0x0000, 0x2500, 0x0F00)),
    'Sunset Orange':  ((0xFFFF, 0x5000, 0x0500), (0x0000, 0x2500, 0x0F00)),
    'Hot Lava':       ((0xFFFF, 0x2000, 0x0000), (0x0000, 0x2500, 0x0500)),
    'Pure White':     ((0xFFFF, 0xC000, 0x6000), (0x0000, 0x1500, 0x2500)),
    'Tropical':       ((0xFFFF, 0x4000, 0x4000), (0x0000, 0x2500, 0x2500)),
    # Cool
    'Forest Green':   ((0x0500, 0xFFFF, 0x1500), (0x1500, 0x0000, 0x1F00)),
    'Jungle':         ((0x3000, 0xFFFF, 0x0500), (0x2500, 0x0000, 0x1500)),
    'Sky Blue':       ((0x2000, 0x6000, 0xFFFF), (0x1500, 0x2500, 0x0000)),
    'Ice':            ((0x6000, 0xC000, 0xFFFF), (0x1F00, 0x1500, 0x0000)),
    'Cyan Teal':      ((0x0500, 0xFFFF, 0xC000), (0x0F00, 0x0000, 0x2500)),
    'Deep Ocean':     ((0x0500, 0x3000, 0xFFFF), (0x0500, 0x2500, 0x0000)),
    # Mood
    'Royal Purple':   ((0x6000, 0x0500, 0xFFFF), (0x2500, 0x0F00, 0x0000)),
    'Magenta Pink':   ((0xFFFF, 0x1000, 0xC000), (0x0000, 0x2000, 0x2500)),
    'Galaxy':         ((0x6000, 0x0000, 0xFFFF), (0x2500, 0x0500, 0x0000)),
    'Aurora':         ((0x0500, 0xFFFF, 0x6000), (0x0F00, 0x0000, 0x2500)),
    # Rainbow — true hue cycle, brightness intentionally varies
    'Rainbow':        ((0xFFFF, 0x0000, 0x0000), (0x0000, 0x0000, 0x0000)),
}

_RAINBOW_STOPS = [
    (0xFFFF, 0x0000, 0x0000),  # red
    (0xFFFF, 0x6000, 0x0000),  # orange
    (0xFFFF, 0xFFFF, 0x0000),  # yellow
    (0x0000, 0xFFFF, 0x0000),  # green
    (0x0000, 0xFFFF, 0xFFFF),  # cyan
    (0x0000, 0x0000, 0xFFFF),  # blue
    (0xC000, 0x0000, 0xFFFF),  # violet
]


def make_colour_var(palette_name, fixture_idx, total_fixtures):
    """Return (R16,G16,B16) for a fixture under the given palette.

    For non-rainbow: anchor + sin(2π·idx/total)·variation. Dominant channel
    of the anchor stays at 0xFFFF (or whatever max it has) on every output,
    so perceived brightness is uniform across the zone.

    For 'Rainbow': true hue walk across fixtures (brightness intentionally
    varies — that's what a rainbow looks like)."""
    if palette_name == 'Rainbow':
        t = fixture_idx / max(1, total_fixtures - 1)
        return _rainbow_lerp(_RAINBOW_STOPS, t)

    anchor, variation = COLOUR_BANK[palette_name]
    if total_fixtures <= 1:
        wave = 0.0
    else:
        wave = math.sin(2 * math.pi * fixture_idx / total_fixtures)
    r = max(0, min(0xFFFF, anchor[0] + int(variation[0] * wave)))
    g = max(0, min(0xFFFF, anchor[1] + int(variation[1] * wave)))
    b = max(0, min(0xFFFF, anchor[2] + int(variation[2] * wave)))
    return (r, g, b)


def _rainbow_lerp(stops, t):
    if t <= 0: return stops[0]
    if t >= 1: return stops[-1]
    n = len(stops) - 1
    seg = t * n
    i = int(seg)
    f = seg - i
    a, b = stops[i], stops[i+1]
    return (int(a[0]+(b[0]-a[0])*f),
            int(a[1]+(b[1]-a[1])*f),
            int(a[2]+(b[2]-a[2])*f))


# ---------------------------------------------------------------------------
# fpStore builders — pass in your project's FIX_UUID map and zone lists.
# These are pure functions that return bytes; they don't know about the
# Builder class, so they're easy to drop into any patcher.
# ---------------------------------------------------------------------------

def fp_palette_uniform_brightness(palette_name, fix_uuid, zones, moving_heads_keys=()):
    """Colour-only preset with anchor+variation across each zone.

    Args:
        palette_name: key into COLOUR_BANK
        fix_uuid: dict of short-name -> UUID string
        zones: list of lists — each inner list is a zone's fixture short-names
               (each zone sweeps the palette independently)
        moving_heads_keys: short-names that need 'shutterState': 1

    Returns: serialised fpStore bytes ready to drop into an LXPreset.

    Declares Color + Intensity=1.0 so pressing it alone is visible. Effects
    Pane (higher priority Intensity) will override intensity when active.
    """
    mh_set = set(moving_heads_keys)
    umbrella = {}
    for zone in zones:
        n = len(zone)
        for idx, k in enumerate(zone):
            r, g, b = make_colour_var(palette_name, idx, n)
            seg = {
                'color': [pack_color(r, g, b)], 'xfadeToColor': 1.0,
                'intensity': 1.0,
            }
            features = ['Color', 'Intensity']
            if k in mh_set:
                seg['shutterState'] = 1
                features = ['Color', 'Intensity', 'Shutter']
            umbrella[fix_uuid[k]] = {
                'definedFeatures': features,
                'fixtureContainer': {},
                'segmentContainers': [seg],
            }
    return plistlib.dumps({'isMutable': False, 'umbrellaContainers': umbrella},
                          fmt=plistlib.FMT_BINARY)


def fp_step(palette_name, fix_uuid, zones, moving_heads_keys=(),
            default_intensity=1.0, intensity_overrides=None):
    """Build a sequence-step fpStore.

    Every fixture gets:
      - colour from anchor+variation (uniform brightness)
      - default_intensity OR a per-fixture intensity override

    `intensity_overrides` is {fixture_short_name: intensity_float} — used to
    make selected fixtures pop above/below others (e.g. one ground bar bright, its mirror dim).

    Returns serialised fpStore bytes.
    """
    overrides = intensity_overrides or {}
    mh_set = set(moving_heads_keys)
    umbrella = {}
    for zone in zones:
        n = len(zone)
        for idx, k in enumerate(zone):
            r, g, b = make_colour_var(palette_name, idx, n)
            i = overrides.get(k, default_intensity)
            seg = {
                'color': [pack_color(r, g, b)], 'xfadeToColor': 1.0,
                'intensity': float(i),
            }
            features = ['Color', 'Intensity']
            if k in mh_set:
                seg['shutterState'] = 1
                features = ['Color', 'Intensity', 'Shutter']
            umbrella[fix_uuid[k]] = {
                'definedFeatures': features,
                'fixtureContainer': {},
                'segmentContainers': [seg],
            }
    return plistlib.dumps({'isMutable': False, 'umbrellaContainers': umbrella},
                          fmt=plistlib.FMT_BINARY)


def fp_dim(fixture_keys, intensity, fix_uuid, moving_heads_keys=()):
    """Intensity-only preset. Used for independent dim zones (house, front
    wash) and for the Effects Pane's static 'ON' / '60%' / 'OFF' buttons."""
    mh_set = set(moving_heads_keys)
    umbrella = {}
    for k in fixture_keys:
        seg = {'intensity': float(intensity)}
        features = ['Intensity']
        if k in mh_set:
            seg['shutterState'] = 1 if intensity > 0 else 2
            features = ['Intensity', 'Shutter']
        umbrella[fix_uuid[k]] = {
            'definedFeatures': features,
            'fixtureContainer': {},
            'segmentContainers': [seg],
        }
    return plistlib.dumps({'isMutable': False, 'umbrellaContainers': umbrella},
                          fmt=plistlib.FMT_BINARY)


# ---------------------------------------------------------------------------
# BPM-derived timing helpers (see docs/patterns.md §15)
# ---------------------------------------------------------------------------

def beat_seconds(bpm):
    """Beat duration in seconds at the given BPM."""
    return 60.0 / bpm


def beat_step_split(bpm, beats_per_step=1.0, hold_fraction=0.25):
    """Return (hold, crossfade) such that hold + crossfade = beat_duration.

    hold_fraction is the share of step time spent holding (vs crossfading).
    Lower hold_fraction = smoother (good for verses). Higher = snappier
    (good for chorus beat hits)."""
    step_total = beat_seconds(bpm) * beats_per_step
    hold = step_total * hold_fraction
    crossfade = step_total - hold
    return (hold, crossfade)

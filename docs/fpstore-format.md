# fpStore format — the inner preset plist

Every `LXPreset` carries a `fpStore` field containing a **separate binary plist** (not NSKeyedArchiver — just a plain bplist). This inner plist is where the actual fixture-state data lives.

## Loading an existing fpStore

```python
import plistlib
fp_bytes = objects[int(preset['fpStore'])]  # raw bytes
inner = plistlib.loads(fp_bytes)
print(inner.keys())
```

## Schema — older (umbrellaContainers)

This is the schema the reference project uses. All current patterns in this documentation target this schema.

```python
{
    'isMutable': False,
    'umbrellaContainers': {
        '<fixture-uuid-string>': {
            'definedFeatures': ['Intensity', 'Color', ...],   # which channels this preset touches
            'fixtureContainer': {
                # per-fixture (not per-beam) settings — rarely used
                # 'speedMode': 1, 'vectorSpeed': 1.0 for moving heads with speed control
            },
            'segmentContainers': [
                {
                    # per-beam state — one entry per fixture segment (most fixtures have 1)
                    'intensity': 0.75,              # 0.0 .. 1.0
                    'color': [packed_color_int64],  # see colour packing below
                    'xfadeToColor': 1.0,            # crossfade amount — always 1.0 for instant colour
                    'panAngle': -0.3,               # radians (moving heads only)
                    'tiltAngle': 1.2,
                    'shutterState': 1,              # 1 = open, 2 = closed, other values = strobe
                    'strobeSpeed': ...,             # if shutter is strobing
                    'coolWhite': ...,               # additional RGB+CW/WW channels
                },
                # ... one segment container per beam for multi-beam fixtures
            ],
        },
        # ... more fixture UUIDs
    },
}
```

### Key facts

- **Each key in `umbrellaContainers` is a fixture UUID string** — specifically, the `UUID` of the `LXDMXFixture` object. Not the beam UUID — these are the same thing in current Lightkey files.
- **Missing fixtures = "don't touch"**. If a preset omits a fixture, Lightkey leaves that fixture's state to whatever lower-priority cue is driving it (or the default). This is how LTP layering works.
- **`definedFeatures`** is an allowlist of what the preset controls. Include ONLY the features you want to drive. A colour-only preset that still includes `'Intensity'` in `definedFeatures` will clobber intensity (even if you didn't set a value).
- **`shutterState`**: 1 = open, 2 = closed. Observed values in the reference project; verify against your specific fixture profile before trusting.

## Schema — newer (containers)

Observed in Lightkey's own Effects Showcase project. The tooling here does not build in this schema yet — contributions welcome (see CONTRIBUTING.md).

```python
{
    'isMutable': False,
    'containers': {
        '<fixture-uuid>': {
            'content': {},          # per-fixture
            'subcontainers': [
                {
                    'content': {
                        # per-beam state: color, intensity, shutterState, etc.
                    },
                },
            ],
        },
    },
}
```

No `definedFeatures` array — features seem to be inferred from which keys are present in `content`. This is a cleaner schema but I haven't reverse-engineered it fully.

## Colour packing

> **CORRECTED 2026-06.** Earlier revisions of this document said red occupied bits 0–15.
> **That is wrong**, and it is the single most expensive error in this documentation's history: a
> whole venue rig was programmed with "fire red" and every fixture rendered **blue**.
> Verified empirically against Lightkey's own native colour picker across 16 hand-named
> presets — every one matched an R↔B transposition with green fixed.

Colour values are stored as **64-bit integers** with four 16-bit channels, **blue lowest**:

```
bits  0-15: Blue   (0x0000 - 0xFFFF)
bits 16-31: Green
bits 32-47: Red
bits 48-63: Alpha  (usually 0x0000 for RGB fixtures)
```

Packing and unpacking in Python:

```python
def pack_color(r16, g16, b16, a16=0):
    return ((b16 & 0xFFFF) | ((g16 & 0xFFFF) << 16) |
            ((r16 & 0xFFFF) << 32) | ((a16 & 0xFFFF) << 48))

def c8(r, g, b):                      # convenience: 8-bit RGB in, packed out
    return pack_color(r * 257, g * 257, b * 257)

def unpack_rgb8(packed):              # for validating your own output
    return (((packed >> 32) & 0xFFFF) >> 8,
            ((packed >> 16) & 0xFFFF) >> 8,
            (packed & 0xFFFF) >> 8)
```

Common colours (16-bit values):

| Name | R | G | B |
|---|---|---|---|
| White | 0xFFFF | 0xFFFF | 0xFFFF |
| Warm white | 0xFFFF | 0xC000 | 0x5000 |
| Red | 0xFFFF | 0x0000 | 0x0000 |
| Amber | 0xFFFF | 0x6000 | 0x0000 |
| Green | 0x0000 | 0xFFFF | 0x0000 |
| Cyan | 0x0000 | 0xFFFF | 0xFFFF |
| Blue | 0x0000 | 0x0000 | 0xFFFF |
| Magenta | 0xFFFF | 0x0000 | 0xFFFF |

(The table is channel values, not bit positions — `pack_color` places them correctly.)

Colour is stored as a **single-element list** in the segment: `'color': [pack_color(...)]`. The list wrapper is required — plain ints are rejected.

### Always prove the byte order on the user's own file

Do not trust this document, and do not trust a symmetric test colour. Before generating a
palette, decode a colour the user made **in Lightkey's GUI** and named unambiguously
("Red", "Deep Blue"). Grey, white and amber-ish colours look identical under either byte
order — pick a saturated primary:

```python
fp = plistlib.loads(objects[int(preset['fpStore'])])
seg = next(iter(fp['umbrellaContainers'].values()))['segmentContainers'][0]
print(hex(seg['color'][0]))       # a GUI-made "Red" must decode red under unpack_rgb8
```

If the user says a colour "comes out wrong on the rig", suspect this before suspecting
fixture wiring or DMX personality — especially when Lightkey's own colour picker behaves
correctly, which proves the fixture profile is fine and the bug is in your packing.

### Ship a calibration row on first colour work

For a new rig, add a temporary row of unmistakable single-hue buttons (`Cal RED`,
`Cal GREEN`, `Cal BLUE`) and ask the user to press each and report what they see. It costs
three cues and settles byte order, fixture profile and colour-mixing questions in one pass.
Remove it once confirmed.

## Writing an fpStore

```python
import plistlib

def build_fpstore(fixture_specs):
    """fixture_specs: {fixture_uuid_str: {
            'defined_features': ['Intensity', 'Color'],
            'segment': {
                'intensity': 1.0,
                'color': [pack_color(0xFFFF, 0, 0)],
                'xfadeToColor': 1.0,
            },
            'fixture_container': {},  # optional
        }}
    Returns the raw bytes to set as the preset's fpStore.
    """
    umbrella = {}
    for fx, spec in fixture_specs.items():
        umbrella[fx] = {
            'definedFeatures': spec['defined_features'],
            'fixtureContainer': spec.get('fixture_container', {}),
            'segmentContainers': [spec['segment']],
        }
    return plistlib.dumps(
        {'isMutable': False, 'umbrellaContainers': umbrella},
        fmt=plistlib.FMT_BINARY,
    )
```

The returned bytes go into `$objects` as a plain bytes entry (no class wrapper), referenced from the preset's `fpStore` field.

## Common segment shapes

### Intensity-only dimmer

```python
{'intensity': 0.5}   # definedFeatures: ['Intensity']
```

### Colour-only (doesn't touch intensity)

```python
{'color': [pack_color(0xFFFF, 0, 0)], 'xfadeToColor': 1.0}
# definedFeatures: ['Color']
```

### Colour + intensity together

```python
{
    'color': [pack_color(0xFFFF, 0, 0)],
    'xfadeToColor': 1.0,
    'intensity': 1.0,
}
# definedFeatures: ['Color', 'Intensity']
```

### Moving head (pan + tilt + intensity + shutter)

```python
{
    'intensity': 1.0,
    'panAngle': -0.3,        # radians; 0.0 = centre
    'tiltAngle': 1.2,        # radians; 0.0 = horizontal, + = up
    'shutterState': 1,       # 1 = open
}
# definedFeatures: ['PanTilt', 'Intensity', 'Shutter']
# fixture_container can optionally include speed: {'speedMode': 1, 'vectorSpeed': 1.0}
```

### Moving head with colour override

```python
{
    'intensity': 1.0,
    'panAngle': -0.3, 'tiltAngle': 1.2,
    'shutterState': 1,
    'color': [pack_color(0xFFFF, 0, 0xFFFF)],
    'xfadeToColor': 1.0,
}
# definedFeatures: ['PanTilt', 'Intensity', 'Shutter', 'Color']
```

### Moving-head practicalities

Learned on a rig of four 105 W beams (540° pan, 180° tilt):

* **`shutterState`: 1 = open, 2 = closed.** An "off" position must set both
  `'intensity': 0.0` **and** `'shutterState': 2` — intensity alone leaves a visible beam on
  some profiles.
* **Mirror the pan, not the tilt.** House-right heads take `-pan` of house-left; tilt is
  shared. A single builder covering both sides removes a whole class of asymmetry bugs:
  ```python
  MOVERS_LEFT, MOVERS_RIGHT = ['MH2', 'MH4'], ['MH1', 'MH3']
  def fp_mh(pan_l, tilt, pan_r=None, inten=1.0, off=False):
      pan_r = -pan_l if pan_r is None else pan_r
      ...
  ```
  If the beams cross when they should splay, flip that sign once at the top rather than
  editing every position.
* **Full feature list** for a position preset is `['Intensity', 'PanTilt', 'Shutter', 'Speed']`,
  with `fixtureContainer = {'speedMode': 1, 'vectorSpeed': 1.0}`.
* **Reference aims** (verify on the user's rig, but these are a sane starting frame):
  `pan 0.0 / tilt -1.127` points down onto the stage; `pan -0.526 / tilt 1.571` points up at
  the ceiling. Tilt ≥ 1.2 is "into the air" — safe, and the only place beams look good
  through haze.
* **A misaligned head is usually physical.** If one head points somewhere the others don't
  while its stored `panAngle`/`tiltAngle` are identical, the problem is the fixture's own
  pan/tilt home or its mounting — not the file. Say so instead of patching offsets in.
* **Movement is a sequence of positions**, with `autoreverses=True` and
  `smoothesFixtureMovements=True`. Slow arcs need a large `crossfadeDuration` (9 s+) and a
  short `holdDuration` (< 1.5 s) — the crossfade *is* the movement.

## The crucial separation: dimmer preset vs colour preset

When building radio groups, make dimmer presets and colour presets **independent** — each targeting only its own features:

```python
# Dimmer preset — intensity only
{
    '<fix_uuid>': {
        'defined_features': ['Intensity'],
        'segment': {'intensity': 0.5},
    }
}

# Colour preset — colour only (NO intensity)
{
    '<fix_uuid>': {
        'defined_features': ['Color'],
        'segment': {'color': [pack_color(r, g, b)], 'xfadeToColor': 1.0},
    }
}
```

If your colour preset also sets `intensity: 1.0`, activating Red while 50%-dim is active will **override your 50% with 100%** because LTP takes the last value for any feature you declared. Keeping them separate lets them layer.

See `patterns.md` for the full radio-group-with-LTP pattern.

---

## The third top-level key: `effects` (native Lightkey effects)

Reverse-engineered from a user-curated reference project. This is how Lightkey's "Effects" pulldown (pulse, multi-colour blend, waterfall chase, etc.) is stored when applied via the GUI.

```python
{
    'isMutable': False,
    'umbrellaContainers': { ... },
    'effects': [  # <-- new top-level array
        {
            'effectClass': 1000,
            'feature': 'Intensity',
            'extent': {
                '<fixture-uuid>': {'all': {}},
                # ... one entry per fixture the effect targets
            },
            'parameters': b'<opaque binary blob>',
            'pixelOrder': {'type': 65536},
            'pixelOrderGranularity': 0,
        },
        # ... multiple effects can stack
    ],
}
```

### Effect class identifiers

Observed values for `effectClass` and the feature they pair with. The skill has no full taxonomy yet — these are confirmed by inspection only:

| effectClass | feature | Observed in |
|---|---|---|
| 1000 | `'Intensity'` | "Dimmer Effect", "Red orange gold slow pulsing" intensity layers — soft pulse curves |
| 1000 | `'Color'` | "Color Effect", "Crashout Effect", "WaterFall" colour layer — colour cycle / chase |
| 2000 | `'PanTilt'` | "Purple w moving lights" — moving head movement |
| 3000 | `'Intensity'` | "Worship just yellow (3) fading", "Worship White Moving (2) 2" — gentler fades |
| 6000 | `'Color'` | "Sky Blue 2", "Blue", many worship scenes — multi-colour blend |

### The `extent` field

A dict keyed by **fixture UUID** (uppercase string), each value being `{'all': {}}`. The effect applies to every listed fixture. This is the field you re-target when cloning an effect to a different fixture set.

### The `parameters` field

An **opaque binary blob** that encodes the actual effect tuning — colour palette, speed, curve shape, randomisation, etc. The format is not reverse-engineered. **You cannot synthesise these bytes from scratch.**

### The `pixelOrder` field

Determines the spatial order in which the effect plays across fixtures (for chases/waterfalls).

```python
'pixelOrder': {'type': 65536}                       # default sequential
'pixelOrder': {'type': 65539}                       # randomised
'pixelOrder': {'type': 524288,                       # custom-ordered
               'orderedPixelRefs': [
                   0.0, [{'fixtureID': '<uuid>'}, ...],
                   1.0, [{'fixtureID': '<uuid>'}],
                   2.0, [{'fixtureID': '<uuid>'}],
                   # ... step index, fixtures-at-that-step
               ]}
```

`orderedPixelRefs` is a flat list alternating `float_step_index, list_of_fixture_refs`. The step index defines firing order; multiple fixtures can fire simultaneously by sharing an index.

## The Clone-and-Retarget pattern

Because `parameters` is opaque, the only reliable way to produce a new "native effect" preset is to clone an effect from a reference file and re-target its extent.

### Extraction (one-time)

```python
import plistlib, pickle
from resolve import load, find_instances
from plistlib import UID

_, refs = load('reference.lightkeyproj')

def getstr(o, ref):
    if not isinstance(ref, UID): return None
    v = o[int(ref)]
    return v if isinstance(v, str) else v.get('NS.string') if isinstance(v, dict) else None

# Save (preset_name, effect_index, effect_dict) tuples
candidates = []
for u in find_instances(refs, 'LXPreset'):
    p = refs[u]
    name = getstr(refs, p.get('name'))
    fp_ref = p.get('fpStore')
    if not isinstance(fp_ref, UID): continue
    fp = plistlib.loads(refs[int(fp_ref)])
    for i, eff in enumerate(fp.get('effects', [])):
        if eff['feature'] != 'Intensity': continue  # filter to intensity effects
        candidates.append((name, i, eff))

with open('intensity_effects.pkl', 'wb') as f:
    pickle.dump(candidates, f)
```

### Cloning into a new preset

```python
import copy

def find_intensity_effect(preset_name, idx):
    for n, i, eff in INTENSITY_FX:
        if n == preset_name and i == idx:
            return copy.deepcopy(eff)
    raise KeyError(f'{preset_name}#{idx}')

def fp_intensity_effect_for(target_keys, ref_preset, ref_idx, baseline=1.0):
    """Build fpStore with a cloned intensity effect retargeted to `target_keys`."""
    eff = find_intensity_effect(ref_preset, ref_idx)
    eff['extent'] = {FIX_UUID[k]: {'all': {}} for k in target_keys}

    umbrella = {}
    for k in target_keys:
        seg = {'intensity': float(baseline)}
        feats = ['Intensity']
        if k in MOVING_HEADS:
            seg['shutterState'] = 1
            feats = ['Intensity', 'Shutter']
        umbrella[FIX_UUID[k]] = {
            'definedFeatures': feats,
            'fixtureContainer': {},
            'segmentContainers': [seg],
        }
    return plistlib.dumps({
        'isMutable': False,
        'umbrellaContainers': umbrella,
        'effects': [eff],
    }, fmt=plistlib.FMT_BINARY)
```

### Why this works

- The `parameters` bytes describe the EFFECT (curve, palette, speed) — they don't bind to specific fixtures.
- The `extent` dict describes WHICH FIXTURES the effect plays on — entirely safe to mutate.
- The `umbrellaContainers` declares the baseline state on each target fixture — separately editable.

So you can take "Pulse Slow" out of one reference preset, point it at a different fixture set, and you've got the same curve playing on new lights.

### Verbatim clone (no retargeting)

When you want to expose Morten's reference scenes as buttons — "Sky Blue", "Red orange gold pulsing", etc. — just copy the entire fpStore bytes without modification. The original UUIDs in `extent` and `umbrellaContainers` reference the same fixtures (assuming the project's UUIDs are unchanged).

```python
def clone_preset(b, name, fp_bytes):
    return mk_preset(b, name, fp_bytes)
```

## When NOT to use the effects array

- **Static colour scenes** — just set `color` in the segment, no effect needed.
- **Per-fixture-varying intensity sequences** — use `LXSequence` with multiple step presets that have explicit per-fixture intensities in `umbrellaContainers`. Native effects apply uniformly across their `extent` and can't express "PN1 bright while PN2 dim" alternation.
- **Beat-locked rhythms** — native effects don't BPM-sync. Use sequence step timing derived from BPM (hold + crossfade = beat duration).


# Patterns

High-level recipes for common Lightkey-patching tasks. Every pattern here has been built and verified to work. When you need to do something, start here before writing code from scratch.

## Contents

1. [Radio groups via preset-group mutual exclusion](#1-radio-groups)
2. [LTP layering (dim + colour independence)](#2-ltp-layering)
3. [Latching vs momentary buttons](#3-latching-vs-momentary)
4. [Scene cues firing multiple presets at once](#4-scene-cues)
5. [Beat-synced sequences](#5-beat-synced-sequences)
6. [Frames with live speed slider](#6-frames-with-speed-slider)
7. [Button tinting via colorName](#7-button-tinting)
8. [Panel layout math](#8-panel-layout-math)
9. §9–§16 — unified Stage Look mutex, colour palettes, per-zone sweeps, priority stacks, selective animation, momentary buttons, BPM timing, designing around LTP
17. [In-place panel redesign — the default for version 2+](#17-in-place-panel-redesign-the-default-for-version-2)
18. [Mirror pairs and centre→edge gradients](#18-mirror-pairs-and-centreedge-gradients)
19. [Layout with build-time collision detection](#19-layout-with-build-time-collision-detection)
20. [Composite "one-press" event cues](#20-composite-one-press-event-cues)
21. [Validate the OUTPUT file, not your intentions](#21-validate-the-output-file-not-your-intentions)
22. [Animated colour flows as sequences](#22-animated-colour-flows-as-sequences)

---

## 1. Radio groups

Problem: several buttons in a section should behave like radio buttons — pressing one deactivates the others.

Solution: **Put all their presets in one `LXPresetGroup` with `presetsAreMutuallyExclusive: True`.** Lightkey does the radio logic natively.

```python
# Build the presets individually
off_preset = mk_preset(b, 'Red Off', build_fpstore({fu: {
    'defined_features': ['Intensity'], 'segment': {'intensity': 0.0}
} for fu in fixtures}))

red_preset = mk_preset(b, 'Red', build_fpstore({fu: {
    'defined_features': ['Color'],
    'segment': {'color': [pack_color(0xFFFF,0,0)], 'xfadeToColor': 1.0}
} for fu in fixtures}))

blue_preset = mk_preset(b, 'Blue', build_fpstore({fu: {
    'defined_features': ['Color'],
    'segment': {'color': [pack_color(0,0,0xFFFF)], 'xfadeToColor': 1.0}
} for fu in fixtures}))

# Wrap them in a cue each (so they can be fired by a button)
red_cue  = mk_cue(b, 'Red',  [red_preset],  priority=4)
blue_cue = mk_cue(b, 'Blue', [blue_preset], priority=4)

# Create the radio group
group = mk_preset_group(b, 'Colour Selector',
                        [off_preset, red_preset, blue_preset],
                        mutually_exclusive=True)
```

The group itself doesn't need to be attached to anything — its existence is enough for Lightkey to enforce the mutual exclusion between its member presets at runtime.

**Do NOT** invent button-level `clusterID` fields. That's my v1 mistake — the schema doesn't support it and Lightkey ignores it.

## 2. LTP layering

Problem: the user wants to set dim level AND colour independently — pressing "Red" shouldn't reset the dim level.

Solution: **separate dim presets and colour presets** into two independent radio groups. Each preset only touches its own features.

```python
# Group A: dimmers — intensity only
dim_off  = mk_dim_preset(b, 'Off',  fixtures, 0.0)
dim_50   = mk_dim_preset(b, '50%',  fixtures, 0.5)
dim_100  = mk_dim_preset(b, '100%', fixtures, 1.0)
mk_preset_group(b, 'Dim (Radio)',
                [dim_off, dim_50, dim_100],
                mutually_exclusive=True)

# Group B: colours — colour only, NO intensity
col_red  = mk_colour_preset(b, 'Red',  fixtures, 0xFFFF, 0, 0)
col_blue = mk_colour_preset(b, 'Blue', fixtures, 0, 0, 0xFFFF)
mk_preset_group(b, 'Colour (Radio)',
                [col_red, col_blue],
                mutually_exclusive=True)
```

The dimmer preset's fpStore has `definedFeatures: ['Intensity']` and only the `intensity` key in segment.

The colour preset's fpStore has `definedFeatures: ['Color']` and only `color` + `xfadeToColor` in segment.

At runtime, Lightkey merges them: `Intensity` comes from whichever dim preset is active, `Color` comes from whichever colour preset is active. They coexist.

**If you declare a feature you don't set a value for**, Lightkey may use a default (0 or undefined) and you'll see surprising behaviour. Only declare what you're driving.

## 3. Latching vs momentary

Buttons have a `behavior` field:

- `behavior: 0` — **latching** (press to turn on, press again to turn off)
- `behavior: 1` — **momentary** (held-on while pressed)

Stage and venue lighting almost always uses latching. Momentary is useful for things like a "MASTER BLACKOUT" hold button or a one-shot flash.

## 4. Scene cues

Problem: the user wants one button that sets multiple sections at once (e.g. "Pre-Service" lights up front wash, sets top colour blue, and turns on haze).

Solution: **one cue, one preset, spec covers ALL fixtures.**

```python
specs = {}
# Front wash at 40%
for k in FRONT_WASH_KEYS:
    specs[FIX_UUID[k]] = {'defined_features': ['Intensity'],
                           'segment': {'intensity': 0.4}}
# Top colour: blue at 30%
for k in TOP_COLOUR_KEYS:
    specs[FIX_UUID[k]] = {'defined_features': ['Color', 'Intensity'],
                           'segment': {
                               'color': [pack_color(0, 0x2000, 0xFFFF)],
                               'xfadeToColor': 1.0,
                               'intensity': 0.3,
                           }}
# Haze on
specs[FIX_UUID['F1']] = {'defined_features': ['Intensity'],
                          'segment': {'intensity': 0.6}}
# Moving heads off
for k in MH_KEYS:
    specs[FIX_UUID[k]] = {'defined_features': ['Intensity', 'Shutter'],
                           'segment': {'intensity': 0.0, 'shutterState': 2}}

p = mk_preset(b, 'Scene: Pre-Service', build_fpstore(specs))
c = mk_cue(b, 'Pre-Service', [p], fade_in=5.0, fade_out=3.0, priority=2)
```

**Priority 2** is below any section radio group (typically 3-10), so hitting a section button after the scene overrides that part. This is usually what the user wants: scene sets a default, then they tweak.

Scene cues typically should set EVERYTHING — including fixtures they want off — so that hitting a different scene doesn't leave stray state from the previous one. Use `'intensity': 0.0` explicitly for "off" fixtures.

## 5. Beat-synced sequences

Problem: need a colour to flash on every beat at 127 BPM.

Solution: **2-step `LXSequence` with timing derived from BPM.**

```python
BEAT = 60.0 / 127  # 0.4724s per beat

# Step 1: bright
bright_specs = {fu: {'defined_features': ['Intensity'], 'segment': {'intensity': 1.0}}
                for fu in fixtures}
p1 = mk_seq_preset(b, 'Flash Bright', build_fpstore(bright_specs))  # note: seq_preset, has 'duration'

# Step 2: dim
dim_specs = {fu: {'defined_features': ['Intensity'], 'segment': {'intensity': 0.2}}
             for fu in fixtures}
p2 = mk_seq_preset(b, 'Flash Dim', build_fpstore(dim_specs))

# Sequence: 2-step cycle, 1 beat total
# cycle = 2 * (hold + crossfade) = BEAT
# So hold + crossfade = BEAT / 2 = 0.236s
seq = mk_sequence(b, 'Beat Flash', [p1, p2],
                  hold=0.1, crossfade=0.136,
                  repeat=0, autoreverses=False)

# Wrap in a cue
cue = mk_cue(b, 'Beat Flash', [seq], fade_in=0.3, fade_out=0.5, priority=10)
```

### Sequence cycle timing cheat sheet

For N steps, autoreverses=False, 2 children:

```
cycle_time = 2 * (hold + crossfade)    # (for 2 steps specifically)
cycle_time = N * (hold + crossfade)    # (general N steps)
```

To pick hold/crossfade for a desired cycle:

```
hold + crossfade = cycle / N
# Choose split based on feel:
# hold big, crossfade small -> sharp transitions
# hold small, crossfade big -> smooth morph
```

### Common tempos

At **127 BPM** (PRAISE, Elevation Worship):
- 1 beat = 0.472s, 8th = 0.236s, 16th = 0.118s, 1 bar = 1.890s

At **128 BPM** (TGIF, Elevation Rhythm):
- 1 beat = 0.469s, 8th = 0.234s, 16th = 0.117s, 1 bar = 1.875s

At **120 BPM** (many hymns):
- 1 beat = 0.500s, 1 bar = 2.000s

### Starting the sequence on the beat

Sequences start from when the cue is activated — meaning the operator must press the button on the downbeat for flashes to land on beats. Live, this is fine with a click track. Without one, drift happens.

See pattern 6 for the speed-slider solution to drift.

## 6. Frames with speed slider

Problem: during a song, the click track drifts slightly and your beat-synced sequences fall out of sync. You want to adjust tempo live without re-triggering cues.

Solution: **wrap song cues in an `LXCpanFrame` with a `speed` metaModifier.** The frame exposes a slider in Lightkey's UI — drag it during the song to speed up or slow down every sequence inside.

```python
# Lay out all song-section buttons first
button_uids = []
for label, cue_uid, tint in song_buttons:
    btn = mk_button(b, cue_uid, x, y, BTN_W, BTN_H, tint=tint)
    button_uids.append(btn)
    x += BTN_W + GAP_X

# Compute bounding box
frame_x = LEFT_MARGIN - 4
frame_y = initial_y
frame_w = (x - LEFT_MARGIN) + 8
frame_h = BTN_H + 22 + 6  # buttons + title area + padding

# Create the frame
frame_uid = mk_cpan_frame(b, 'PRAISE — 127 BPM',
                          frame_x, frame_y, frame_w, frame_h,
                          button_uids,
                          show_speed_slider=True,
                          priority=10)

# Both buttons AND frame get added to panel.items
panel_items = button_uids + [frame_uid, ...]
```

Important details:

- **Buttons live in `panel.items` directly** AND are referenced from `frame.members` (NSSet). Both places, same UIDs.
- **Buttons use absolute panel coordinates** — the frame rect is a bounding-box overlay, not a coordinate origin.
- Frame's `metaModifiers` NSDictionary contains the 3 default sliders: `fadeTime`, `intensity`, `speed` (all 1.0). Lightkey renders these as on-screen knobs.
- `LXCpanFrame` and `LXCanvasItem` class defs may not exist in your source file — this documentation's patcher can add them if needed.

## 7. Button tinting

Button backgrounds can be tinted using `colorName`, a **raw string** (not NSString).

Valid AppKit colour names observed to work in Lightkey:
- `Red`, `Orange`, `Yellow`, `Green`, `Blue`, `Purple`, `Gray`

No `Cyan` or `Magenta` — map Cyan to `Blue`, Magenta to `Purple`.

No custom hex colours — only these seven names.

```python
color_name_uid = b.raw_str('Red') if tint else UID(0)
# ... in the button dict:
{'colorName': color_name_uid, ...}
```

**Use tinting sparingly.** Tint the colour buttons (Red → Red tint, Blue → Blue tint) but not the Off/dim/FX buttons. Makes the panel scannable in a dark room without being visually noisy.

## 8. Panel layout math

Lightkey panels use a simple 2D coordinate system in points, origin top-left. Typical values:

```python
BTN_W = 100          # button width (decent readability with most labels)
BTN_H = 36           # button height (matches Lightkey defaults)
GAP_X = 4            # horizontal gap between buttons in a row
GAP_Y = 4            # vertical gap between rows
SECTION_GAP = 18     # extra gap between sections
LABEL_H = 22         # height for section text labels
LEFT_MARGIN = 15     # panel left padding
TOP_MARGIN = 20      # panel top padding
```

Rect strings use format `'{{x, y}, {w, h}}'` and are stored as raw plist strings (no class wrapper).

```python
rect = f'{{{{{x}, {y}}}, {{{w}, {h}}}}}'
rect_uid = archive['$objects'].append(rect)  # plain string, gets its own UID
# OR use a builder helper: rect_uid = b.raw_str(rect)
```

### Layout loop

Typical layout is row-based, section by section:

```python
y = TOP_MARGIN
for section_label, rows in sections:
    # (Optional) section label
    items.append(mk_text_label(b, section_label, label_cx, label_cy, lw, LABEL_H))
    y += LABEL_H + LABEL_TO_ROW_GAP

    for row in rows:
        x = LEFT_MARGIN
        for button_label, cue_uid, tint in row:
            items.append(mk_button(b, cue_uid, x, y, BTN_W, BTN_H, tint=tint))
            x += BTN_W + GAP_X
        y += BTN_H + GAP_Y

    y += SECTION_GAP - GAP_Y  # extra breathing room before next section
```

### Sizing for wider rows

If a section has many buttons (e.g. 13 house-lights dimmer values), use narrower buttons:

```python
BTN_W_NARROW = 72    # fits ~15 across in a 1100-wide panel
```

13 × 72 + 12 × 4 = 984 points. Comfortable on a laptop screen.

### Panel total size

Lightkey auto-sizes the panel to fit the largest item, but aim for something sensible:
- **Width:** 1000-1200pt (fits most laptop displays without scrolling)
- **Height:** whatever is needed, but users can scroll

Long panels (>1500pt tall) start to feel unwieldy. Consider multi-page navigation (`showsBackButton`/`showsForwardButton` on frames) — though in this documentation's experience, page changes cause light state to reset, so keep things on one page where possible.

---

## 9. Unified mutually-exclusive group ("Stage Look")

Problem: you have multiple ways to set stage colour — a palette bank, song sequences, cloned reference scenes — and they live in different sections of the panel. Activating one without deactivating the others causes UI confusion (multiple buttons highlight) AND LTP conflicts (a hidden higher-priority cue out-renders the visible button selection).

Solution: put EVERY colour-driving cue (palettes, sequences, FX) into ONE `LXPresetGroup` with `presetsAreMutuallyExclusive: True`, regardless of which panel section the button lives in. The group is invisible UX — its only job is mutex.

```python
cb_uids   = build_colour_bank(b)         # 16 palettes
itg_uids  = build_i_thank_god(b)         # 4 song sequences
fx_uids   = build_colour_bearing_fx(b)   # 3 cloned scenes

mk_preset_group(b, 'Stage Look',
                cb_uids + itg_uids + fx_uids,
                mutually_exclusive=True)
```

Pressing any one button deactivates all the others. The highlighted button on screen always matches what's on stage. No zombie cues.

**Don't** put intensity-only cues (Effects Pane, House dim) in this group — they compose freely with the colour layer and must stay active independently.

## 10. Anchor + variation colour palettes (uniform brightness)

Problem: a palette defined as a list of stops (e.g. Sky Blue = `[pale, cerulean, azure, deep]`) renders fixtures with visibly different brightness because the RGB amplitudes themselves differ. `(0x9000, 0, 0)` reads dimmer than `(0xFFFF, 0x6000, 0)` even at the same intensity. Looks amateur.

Solution: define each palette as a (anchor, variation) tuple where the anchor's dominant channel is `0xFFFF` and the variation perturbs only the secondary channels. Every fixture renders the same brightness; only hue drifts.

```python
COLOUR_BANK = {
    # anchor RGB,                       variation RGB amplitudes
    'Fire Red':       ((0xFFFF, 0x0500, 0x0500), (0x0000, 0x2500, 0x0F00)),
    'Forest Green':   ((0x0500, 0xFFFF, 0x1500), (0x1500, 0x0000, 0x1F00)),
    'Sky Blue':       ((0x2000, 0x6000, 0xFFFF), (0x1500, 0x2500, 0x0000)),
    # ... etc — keep the anchor's max channel at 0xFFFF, set variation
    # to zero on that channel, modest on the others.
}

def make_colour_var(palette_name, fixture_idx, total_fixtures):
    """Anchor + sin(2π·idx/total)·variation per fixture."""
    import math
    anchor, variation = COLOUR_BANK[palette_name]
    wave = math.sin(2 * math.pi * fixture_idx / max(1, total_fixtures))
    r = max(0, min(0xFFFF, anchor[0] + int(variation[0] * wave)))
    g = max(0, min(0xFFFF, anchor[1] + int(variation[1] * wave)))
    b = max(0, min(0xFFFF, anchor[2] + int(variation[2] * wave)))
    return (r, g, b)
```

Result: a "Fire Red" preset has 6 distinct red shades across 6 top-bar fixtures, all at the same perceived brightness. Modern professional look without effort from the operator.

Exception: rainbows are inherently brightness-varied (yellow has 2 channels at full, red has 1). Just accept that for rainbow palettes.

## 11. Per-zone full-palette sweep

Problem: spreading one global gradient across 22 stage fixtures means a 6-fixture top bar only covers indices 0–5 — the first ~25% of the palette. All six fixtures land near `palette[0]` and look monochrome.

Solution: each ZONE gets its own full sweep across the palette. Top bar of 6 walks 0→1 across the whole palette; backwards lights of 5 do the same independently.

```python
def fp_colour_palette(palette_name):
    umbrella = {}
    zones = [TOP_BAR, SIDE_VERTICAL, BACKWARDS, GROUND, MOVING_HEADS]
    for zone in zones:
        n = len(zone)
        for idx, k in enumerate(zone):
            r, g, b = make_colour_var(palette_name, idx, n)
            umbrella[FIX_UUID[k]] = {
                'definedFeatures': ['Color', 'Intensity'],
                'fixtureContainer': {},
                'segmentContainers': [{
                    'color': [pack_color(r, g, b)], 'xfadeToColor': 1.0,
                    'intensity': 1.0,
                }],
            }
    return plistlib.dumps({'isMutable': False, 'umbrellaContainers': umbrella},
                          fmt=plistlib.FMT_BINARY)
```

Top bar P8–P13 visits Sky Blue's full range: pale sky → cerulean → azure → deep blue → midnight. Backwards lights independently walk the same palette across their 5 fixtures. Every zone reads as "colour-walked" not "monochrome chunk".

## 12. Priority stack for layered composition

Problem: you want Colour Bank + Effects Pane to compose freely; you want song sequences to "seal" their look (Effects can't clobber them); you want MC/Preach scenes to override everything below.

Solution: assign per-LAYER priorities. LTP is per-feature, so layers that drive different features (Color vs Intensity) compose regardless. Layers driving the SAME feature stack by priority — higher wins.

```
Front Wash / Preach Corner   3     # independent fixture zone (no conflict)
House                        4     # independent zone
Haze                         5     # independent zone
Stage Look (Colour Bank)     6     # base — Color + Intensity at 1.0
Effects Pane                 7     # Intensity only — wins over Stage Look's Intensity
Song sequences (e.g. ITG)    8     # Color + Intensity per-fixture — wins over Effects Pane
MC / Preach scenes           9     # cloned, both features — overrides everything below
Master Blackout              11    # full takeover when triggered
Punch FX (momentary)         12    # press-and-hold flashes that punch through
```

Why this works:

- Colour Bank press: `Color` + `Intensity=1.0` at p6. Both features visible.
- Add Effects Pane press: `Intensity` (with effect) at p7. Wins LTP on Intensity. Colour Bank's `Color` is uncontested and still visible.
- Add song sequence press: `Color` + per-fixture `Intensity` at p8. Wins both. Sequence's selective animation isn't clobbered.
- Add MC press: full takeover at p9. Stage look frozen on MC's scene.
- Hold a Punch FX button at p12: momentary override during the press, releases on lift.

The trade-off: when a sequence is active, Effects Pane can't compose with it (sequence's per-fixture intensity wins). That's the right call — sequences are intentional "complete looks" not modular layers.

## 13. Selective fixture animation in sequence steps

Problem: a sequence where every fixture flashes together looks amateur ("disco strobe"). A pro show animates SELECTED fixtures and leaves the rest steady.

Solution: each sequence step's fpStore declares per-fixture intensity overrides on top of a uniform baseline. Only the called-out fixtures pop; the rest hold steady.

```python
def fp_step(palette_name, default_intensity=1.0, intensity_overrides=None):
    """Sequence-step fpStore: anchor+variation colour, uniform default intensity,
    per-fixture intensity overrides for selective animation."""
    overrides = intensity_overrides or {}
    umbrella = {}
    for zone in [TOP_BAR, SIDE_VERTICAL, BACKWARDS, GROUND, MOVING_HEADS]:
        n = len(zone)
        for idx, k in enumerate(zone):
            r, g, b = make_colour_var(palette_name, idx, n)
            i = overrides.get(k, default_intensity)
            seg = {'color': [pack_color(r, g, b)], 'xfadeToColor': 1.0,
                   'intensity': float(i)}
            feats = ['Color', 'Intensity']
            if k in MOVING_HEADS:
                seg['shutterState'] = 1
                feats = ['Color', 'Intensity', 'Shutter']
            umbrella[FIX_UUID[k]] = {
                'definedFeatures': feats, 'fixtureContainer': {},
                'segmentContainers': [seg],
            }
    return plistlib.dumps({'isMutable': False, 'umbrellaContainers': umbrella},
                          fmt=plistlib.FMT_BINARY)
```

### Example: chorus PN1 ↔ PN2 alternate-flash at 78 BPM

```python
# 4 steps × 1 beat each = 1 bar at 78 BPM (= 0.77s per step)
chorus_steps = [
    # All zones uniform 1.0 except PN1/PN2 alternating
    {'PN1': 1.00, 'PN2': 0.30},
    {'PN1': 0.30, 'PN2': 1.00},
    {'PN1': 1.00, 'PN2': 0.30},
    {'PN1': 0.30, 'PN2': 1.00},
]
seq_preset_uids = [
    mk_seq_preset(b, f'ITG Chorus step {i+1}',
                  fp_step('Sunset Orange', default_intensity=1.0,
                           intensity_overrides=ovr))
    for i, ovr in enumerate(chorus_steps)
]
# Hold 0.18 + xfade 0.59 = 0.77s = 1 beat at 78 BPM
seq = mk_sequence(b, 'ITG Chorus Seq', seq_preset_uids,
                  hold=0.18, crossfade=0.59, autoreverses=False)
```

### Example: L→R chase across top bar with neighbour glow

```python
TOP = TOP_BAR  # ['P8', 'P9', 'P10', 'P11', 'P12', 'P13']
bridge_steps = []
for active_idx in range(len(TOP)):
    overrides = {}
    for fx_idx, fx_key in enumerate(TOP):
        distance = abs(fx_idx - active_idx)
        if distance == 0:   overrides[fx_key] = 1.00   # leading fixture
        elif distance == 1: overrides[fx_key] = 0.55   # neighbour glow
        else:               overrides[fx_key] = 0.20   # far fade
    bridge_steps.append(overrides)
```

The chase reads as professional movement, not a strobe.

## 14. Momentary buttons (press-and-hold)

Problem: latching FX buttons (white flash, top flash) end up "stuck on" because the operator never thinks to press them again to release. They quietly override your Stage Look until noticed.

Solution: `behavior: 1` on the `LXCpanButton` makes it momentary — active only while held, releases on lift.

```python
def mk_button_momentary(b, cue_uid, x, y, w, h, tint=None):
    rect_uid = b.raw_str(f'{{{{{x}, {y}}}, {{{w}, {h}}}}}')
    color_name = b.raw_str(tint) if tint else UID(0)
    return b.add({
        'cue': cue_uid, 'rect': rect_uid,
        'type': 0, 'behavior': 1,   # 1 = momentary
        'vertical': False,
        'titleAlignment': 0, 'titleUnderlineStyle': 0,
        'clusterRequiresSelection': False,
        'colorName': color_name, 'titleFont': UID(0),
        '$class': b.cls('LXCpanButton'),
    })
```

Use for: white flashes, momentary blackouts, any "punch through" cue at priority ≥ 11 that should auto-release.

## 15. BPM-derived sequence timing cheat sheet

For sequence step duration:

```
step_duration = hold + crossfade
```

To hit one beat per step at a known BPM:

```
beat_duration_seconds = 60.0 / BPM
```

Split between hold and crossfade based on the feel you want:

```
hold ≪ crossfade   → smooth morph between steps (good for verse, ballads)
hold ≈ crossfade   → balanced (good for build sections)
hold ≫ crossfade   → sharp transitions (good for chorus beat hits, strobes)
```

### Reference table

| BPM | Beat | 8th | 16th | 1 bar |
|---|---|---|---|---|
| 78  (I Thank God / slow worship)    | 0.769s | 0.385s | 0.192s | 3.077s |
| 100 (mid worship)                   | 0.600s | 0.300s | 0.150s | 2.400s |
| 114 (gospel mid-tempo)              | 0.526s | 0.263s | 0.132s | 2.105s |
| 120 (common hymn)                   | 0.500s | 0.250s | 0.125s | 2.000s |
| 127 (PRAISE Elevation)              | 0.472s | 0.236s | 0.118s | 1.890s |
| 128 (TGIF Elevation Rhythm)         | 0.469s | 0.234s | 0.117s | 1.875s |

### Example: 78 BPM 1-beat-per-step with a snappy feel

```python
# beat = 0.77s, want hold ≫ crossfade for sharp beat hits
hold = 0.18
crossfade = 0.59
# hold + crossfade = 0.77 ✓
```

## 16. Don't fight LTP — design around it

Lightkey's LTP (latest-takes-priority) layers per-feature. The system can express:

- ✅ "All fixtures share this colour; their intensity varies independently."
- ✅ "Some fixtures hold steady while others animate."
- ✅ "Higher-priority layer overrides lower-priority on the features it declares."

It can NOT express:

- ❌ "Effect modulates intensity RELATIVELY (multiplied) on top of a baseline."
- ❌ "Mix two colour palettes 50/50 across all fixtures."
- ❌ "Two cues both at full priority decide together — last write loses but the other still partially shows."

When designing your control surface, work with LTP. If you want intensity composition, separate dimmer cues (Intensity-only) from colour cues (Color-only). If you want sealed sequence looks, raise their priority above the Effects Pane. If you want "OFF" buttons, make them an explicit cue (intensity 0, no colour) and let mutex handle the rest.


---

## 17. In-place panel redesign (the default for version 2+)

Once a user has edited their project in Lightkey, **modify their panel instead of replacing
it**. This preserves every binding (Bug 21), every customisation (Bug 22), and keeps the
`selectedLivePanel` pointer valid so the file opens on the right tab.

The shape of the whole build:

```python
archive = plistlib.load(open(SRC, 'rb'))
top, objs = archive['$top'], archive['$objects']
b = Builder(archive)

stage_look = find_group('v18 Stage Look')     # by NAME — UIDs shift (Bug 23)
movers_grp = find_group('v18 Movers')

# 1. classify existing buttons into sections, keeping the objects themselves
panel = objs[int(top['selectedLivePanel'])]
for iu in objs[int(panel['items'])]['NS.objects']:
    ob = objs[int(iu)]
    if cn(ob) == 'LXCpanButton':
        nm = gs(objs[int(ob['cue'])].get('name'))
        key = classify(nm)
        if key == 'UNKNOWN':
            raise SystemExit(f'unclassified button: {nm!r}')   # never drop user work
        sect.setdefault(key, []).append((nm, iu))

# 2. build NEW capability, appending presets into the EXISTING mutex groups (Bug 25)
p = mk_preset(b, 'Col Coral', fp_scene3(stops, 0.88))
group_append(stage_look, p)
new_cue = mk_cue(b, 'Coral', [p], fade_in=2.0, fade_out=2.0, priority=6)

# 3. re-lay out: reposition reused buttons, mint buttons only for new cues
ob['rect'] = b.raw_str(f'{{{{{x}, {y}}}, {{{w}, {h}}}}}')

# 4. same panel object, new item list
panel['items'] = b.ns_array(items)
panel['name'] = b.raw_str('Modular Panel v20')
```

Ordering within a section is worth doing explicitly. Two rules cover most cases:

```python
def _level_key(pair):                     # House/Front Wash/Preach rows
    nm = (pair[0] or '').lower()
    if 'off' in nm:
        return -1                          # Off first
    m = re.search(r'(\d+)\s*%', nm)
    return int(m.group(1)) if m else 999    # then numerically ascending

ORDER = {'FLOW': ['Warm Glow Flow', 'Sunset Flow', ...]}   # explicit for the rest
sect[k].sort(key=lambda p: ORDER[k].index(p[0]) if p[0] in ORDER[k] else 99)
```

A user reading "Off | 60% | 100% | 30%" reads it as a bug, even though every button works.

## 18. Mirror pairs and centre→edge gradients

For a symmetric stage, colour looks read as *designed* rather than random when fixtures are
coloured by their **mirrored position**, not their patch order.

```python
MIRROR_PAIRS = [('P10','P11'), ('P9','P12'), ('P8','P13'), ('MH2','MH1'), ...]
POS_X = {'P8': 13, 'P9': 30, ...}          # real stage X from the user's plan
CENTRE_X = 90.0

# normalise each pair's distance from centre to t ∈ [0, 1]
_pd = [(l, r, mean(abs(POS_X[k] - CENTRE_X) for k in {l, r})) for l, r in MIRROR_PAIRS]
_lo, _hi = min(d for *_, d in _pd), max(d for *_, d in _pd)
PAIRS_T = [(l, r, (d - _lo) / (_hi - _lo)) for l, r, d in _pd]
```

Then every look is a function of `t`, and left/right get identical colour by construction —
which is what "top-left matches top-right" means to a lighting operator.

**Two-stop looks** (`lerp(c0, c1, t)`) read as a single wash. **Three-stop looks** —
deepest and most saturated at centre, richest in the mid, lightest at the edges — read as
dimensional and are worth the extra parameter:

```python
def fp_scene3(stops3, tier_int):
    c0, c1, c2 = stops3
    for lk, rk, t in PAIRS_T:
        rgb = lerp(c0, c1, t * 2) if t <= 0.5 else lerp(c1, c2, (t - 0.5) * 2)
        ...
```

To deepen an existing 2-stop palette without changing its family, push saturation up and
value slightly down at the centre, and the reverse at the edge:

```python
def _hsv_push(rgb, s_mul, v_mul):
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    return tuple(int(round(c * 255))
                 for c in colorsys.hsv_to_rgb(h, min(1, s * s_mul), min(1, v * v_mul)))

deep = (_hsv_push(c0, 1.18, 0.93), _hsv_push(mid, 1.10, 1.0), _hsv_push(c1, 0.94, 1.06))
```

Leave whites alone — pushing saturation on a white look just tints it.

## 19. Layout with build-time collision detection

Never lay out a panel with a bare cursor. Track every placed box and refuse to place an
overlapping one; the build fails loudly instead of shipping a panel with text under buttons
(Bug 24).

```python
boxes = []
def add_box(x, y, w, h, desc):
    for (px, py, pw, ph, pd) in boxes:
        if not (x >= px + pw or px >= x + w or y >= py + ph or py >= y + h):
            raise SystemExit(f'OVERLAP: {desc} vs {pd}')
    boxes.append((x, y, w, h, desc))
```

A header helper that puts the hint beside the title when it fits and below it when it
doesn't, returning the new cursor, keeps sections uniform:

```python
def header(x0, colw, y, title, hint):
    tw = min(colw, len(title) * 16 + 30)
    add_box(x0, y, tw, TITLE_H, f'title:{title}')      # TITLE_H = 35 for 24pt
    items.append(mk_text(title, x0 + tw/2, y + TITLE_H/2, tw, TITLE_H, attrs24))
    hw = len(hint) * 7.2 + 24                          # 13pt
    if tw + 12 + hw <= colw:                           # inline
        add_box(x0 + tw + 12, y + 8, hw, HINT_H, f'hint:{title}')
        ...
        return y + TITLE_H + 8
    add_box(x0, y + TITLE_H + 2, min(colw, hw), HINT_H, f'hint:{title}')   # below
    ...
    return y + TITLE_H + 2 + HINT_H + 8
```

**Two-column dashboards** work well for live use: left column in service order (master →
house → face light → colour → effects), right column for the things touched independently
(speaking scenes, movers, haze, momentary punches). Give the right column short hints — the
narrow width is what forces a hint onto its own line and eats vertical space.

Then re-verify from the written file (see §21).

## 20. Composite "one-press" event cues

A single button that changes several feature domains at once — the pattern behind a party or
worship "mode" — is a cue whose `presets` array spans several groups:

```python
cue = mk_cue(b, 'PARTY MODE', [
    colour_cycle('Party GoldRose', STOPS, hold=1.2, xfade=6.0),  # -> Stage Look mutex
    air_sweep('Party', hold=0.8, xfade=9.0),                     # -> Movers mutex
    haze_preset('Party Haze', 0.55),                             # loose, no mutex
], fade_in=3.0, fade_out=3.0, priority=6)
```

Design notes that made this look professional rather than gimmicky:

* **Slow is elegant.** Colour: `hold ≈ 1.2s`, `xfade ≈ 6s` per stop — a 6–8 stop palette then
  takes ~1 minute per revolution. Movers: `xfade 9s+` with `autoreverses=True` and
  `smoothesFixtureMovements=True`.
* **A "slower" variation must actually slow the movers too**, not just the colour. Users
  notice; a variation that only changes the colour timing reads as broken.
* **Aim beams up into the air** (tilt ≥ 1.2 rad on a 180° head) rather than across the room.
  Sweeping the ceiling through haze looks intentional and never blinds anyone.
* **Keep the palette inside one warm or one cool family.** Cycling the full spectrum looks
  like a disco preset; gold → amber → copper → rose → blush looks designed.
* **Ship an explicit exit cue** with a member in every group the composite touched (Bug 26).

## 21. Validate the OUTPUT file, not your intentions

Structural parity checks (class defs, key sets, raw-string names) catch decode crashes. They
do not catch a panel that opens fine and is unusable. Re-parse the written file and assert
the *semantics* you promised:

| Claim you made to the user | Assertion on the output file |
|---|---|
| "your buttons all still work" | every reused button UID present, `cue`/`behavior`/`colorName` identical to source |
| "text is never hidden" | zero pairwise intersection over all button rects + label `center ± size/2` |
| "labels are readable" | every label's box height ≥ its `NSFont.NSSize` × 1.4 |
| "the rockers still work" | every mutex group still `presetsAreMutuallyExclusive`; old child set ⊆ new child set |
| "new colours join the rocker" | each new cue's colour preset ∈ that group's `childNodes` |
| "party is warm gold & rose" | decode every sequence step's colour, bucket hue, assert ⊆ {red, orange, yellow, magenta, white} |
| "movers aim high and slow" | every `tiltAngle` ≥ 1.0; `crossfadeDuration` ≥ 9.0; slower variant strictly greater |
| "looks are deeper now" | ≥ 3 distinct RGB stops per look; hue set within the expected family; output differs from source |

Decoding colours back out (`unpack_rgb8` → HSV → hue bucket) is the only way to catch a
byte-order regression, and it is cheap. A validator in this shape caught real problems in
every version; 64 assertions is not excessive for a file a volunteer will run a service on.

## 22. Animated colour flows as sequences

Users ask for the look of Lightkey's native WaterFall / Color Cycle effects **in their own
palette**. You cannot do that by cloning: a native effect's colours live inside the opaque
`parameters` blob of the `effects` array (see `fpstore-format.md`), which is not
introspectable or repaintable. Clone it verbatim or not at all.

Build the equivalent as a sequence instead — this is what shipped and what the user
described as the effect they wanted:

```python
def flow(name, stops, hold=0.7, xfade=2.8, tier_int=0.82):
    """Rotate a palette across mirror-pair rank — a gentle travelling wash."""
    steps = [mk_preset(b, f'{name} s{i}', fp_flow_step(stops, i, tier_int), duration=-1.0)
             for i in range(len(stops))]
    return mk_seq(b, f'{name} Seq', steps, hold=hold, xfade=xfade,
                  repeat=0, autorev=False, smooth=False)

def fp_flow_step(stops, offset, tier_int):
    n = len(stops)
    for rank, (lk, rk, _t) in enumerate(PAIRS_T):          # rank = centre→edge order
        rgb = stops[(rank + offset) % n]                   # rotate one stop per step
        ...
```

Properties worth keeping:

* `duration: -1.0` on every child preset (Bug 7), `repeat=0` for infinite.
* `autoreverses=False` for colour (a colour flow should travel one way);
  `autoreverses=True` for mover movement (a beam should come back).
* `smoothesFixtureMovements=False` for colour-only sequences — it only applies to pan/tilt
  and costs nothing to leave off.
* 6 stops at `hold 0.7 / xfade 2.8` gives a ~21 s revolution, which reads as "gentle". Same
  machinery at `hold 1.2 / xfade 6.0` gives the ~1 min elegant party cycle (§20).
* Because it's mirror-pair ranked, left and right stay symmetric while the colour travels.

Put these sequences in the same mutex group as the static colour looks (§9) — they are
colour-bearing, so they must release, and be released by, the static bank.

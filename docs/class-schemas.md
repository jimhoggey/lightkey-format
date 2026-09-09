# Class schemas

Exact field-by-field schemas for every Lightkey class that can be safely constructed by this documentation. Derived from inspecting real Lightkey files.

**When building any of these:** find an existing instance in the source file first and diff your keys against its keys. Missing or extra keys cause NSKeyedUnarchiver to fail silently.

## Table of contents

1. [LXPreset](#lxpreset)
2. [LXPresetGroup](#lxpresetgroup)
3. [LXRootPresetGroup](#lxrootpresetgroup)
4. [LXCue](#lxcue)
5. [LXSequence](#lxsequence)
6. [LXControlPanel](#lxcontrolpanel)
7. [LXCpanButton](#lxcpanbutton)
8. [LXCpanFrame](#lxcpanframe)
9. [LXTextCanvasItem](#lxtextcanvasitem)
10. [NSTextStorage](#nstextstorage)
11. [Bindings (MIDI, keyboard)](#bindings-midi-keyboard)
12. [Fixture profiles and capabilities](#fixture-profiles-and-capabilities)
13. [NSString / NSMutableString / NSUUID / NSArray / NSDictionary / NSSet](#ns-classes)

---

## LXPreset

A fixture-state snapshot. The heart of every cue.

**Class chain:** `['LXPreset', 'NSObject']`

```python
{
    'name': UID(),           # -> NSMutableString
    'UUID': UID(),           # -> NSUUID
    'active': False,         # bool — always False at build time
    'childNodes': UID(),     # -> NSArray (usually empty shared singleton)
    'fpStore': UID(),        # -> raw bytes (inner binary plist, see fpstore-format.md)
    '$class': UID(),         # -> class def for LXPreset
}
```

### Variant: sequence child preset

When used as a child of an `LXSequence`, adds one field:

```python
{
    # ...same as above, plus:
    'duration': -1.0,        # float — per-step hold time; -1.0 means use sequence default
}
```

**Gotcha:** if a preset is meant to be a sequence child, it MUST have `duration`; standalone presets must NOT. Mixing these confuses Lightkey.

---

## LXPresetGroup

A container grouping preset(s) with optional mutual exclusion (radio behaviour).

**Class chain:** `['LXPresetGroup', 'NSObject']`

```python
{
    'name': UID(),           # -> NSMutableString (can be empty)
    'UUID': UID(),           # -> NSUUID
    'childNodes': UID(),     # -> NSArray of LXPreset / LXPresetGroup / LXSequence UIDs
    'presetsAreMutuallyExclusive': True or False,  # bool — radio behaviour
    '$class': UID(),
}
```

**Radio behaviour:** set `presetsAreMutuallyExclusive: True` and activating one preset in the group auto-deactivates the others. This is Lightkey's NATIVE radio mechanism — do not invent button-level `clusterID` fields, they don't exist.

---

## LXRootPresetGroup

Top-level preset tree root, AND the "orphanPresetsGroup" required by every cue.

**Class chain:** `['LXRootPresetGroup', 'NSObject']` (confirm with your source)

```python
{
    'name': UID(),           # -> NSMutableString (e.g. 'Cue Orphan Presets Group')
    'UUID': UID(),           # -> NSUUID
    'childNodes': UID(),     # -> NSArray (usually the empty singleton)
    'presetsAreMutuallyExclusive': False,
    '$class': UID(),
}
```

**Critical:** every `LXCue` must have an `orphanPresetsGroup` pointing to a fresh `LXRootPresetGroup` of its own. Sharing one between cues will crash Lightkey.

---

## LXCue

The primary playable unit — fires one or more presets/sequences with fade-in/out timing.

**Class chain:** `['LXCue', 'LXCueObjC', 'NSObject']` — note the middle layer.

```python
{
    'name': UID(),               # -> NSMutableString
    'UUID': UID(),               # -> NSUUID
    'active': False,
    'activateAtStartup': False,
    'activateAtShutdown': False,
    'excludeFromLiveTriggers': False,
    'requiresUnlockedApp': False,
    'fadeInDuration': float,     # seconds
    'fadeOutDuration': float,    # seconds
    'fadeDuration': 0.5,         # seconds — legacy default, keep at 0.5
    'holdDuration': -1.0,        # -1.0 = hold indefinitely; > 0 = auto-release
    'priority': int,             # LTP priority; higher wins. Typical range 1-10
    'intensity': 1.0,            # overall intensity scale
    'presets': UID(),            # -> NSArray of LXPreset and/or LXSequence UIDs
    'orphanPresetsGroup': UID(), # -> LXRootPresetGroup (must be unique per cue)
    'metaModifiers': UID(),      # -> NSDictionary (empty singleton OK)
    'metaModifierDefaults': UID(),   # -> SAME empty NSDictionary singleton
    'activeSpeedModifiers': UID(),   # -> NSSet (empty OK) — CRITICAL: NSSet not NSArray!
    'intensityFeatures': UID(0), # -> $null (UID 0)
    '$class': UID(),
}
```

**CRITICAL GOTCHAS:**

- `activeSpeedModifiers` must be an **NSSet**, not an NSArray. Even though it's commonly empty, the class check is strict.
- `metaModifiers` and `metaModifierDefaults` should point to the **same shared empty NSDictionary**, not two separate dicts.
- `orphanPresetsGroup` must be a **fresh** LXRootPresetGroup per cue.
- `presets` may contain a mix of LXPreset and LXSequence UIDs — Lightkey accepts both.

---

### Timing fields that matter

* `holdDuration`: `-1.0` = stay active until released (GUI default). **A finite value (seconds)
  makes the cue release itself** after fade-in + hold — a one-shot. Verified on hardware; see
  `patterns.md` §23.
* `fadeInDuration` / `fadeOutDuration`: crossfade in/out. On a cue carrying `PanTilt`, fade-in is
  the **travel time** of the heads.
* `priority`: higher wins per feature (LTP inside equal priority). Reference stack in
  `patterns.md` §12/§24.
* `activateAtStartup`: the one cue Lightkey fires on open (keep the user's).

## LXSequence

A beat-synced or time-based cycle through a list of preset-state snapshots.

**Class chain:** `['LXSequence', 'NSObject']` (confirm with your source)

```python
{
    'name': UID(),                    # -> NSMutableString
    'UUID': UID(),                    # -> NSUUID
    'active': False,
    'childNodes': UID(),              # -> NSArray of sequence-child LXPreset UIDs (with 'duration' field)
    'presetsAreMutuallyExclusive': False,
    'random': False,
    'beatQuantum': 1,                 # beat-counter resolution
    'reversed': False,
    'holdDuration': float,            # seconds per step (ignored for -1.0 children)
    'hasVariableFadeTimes': False,
    'autoreverses': True or False,    # ping-pong on end? (A→B→A→B pattern)
    'beatMultiplier': 24,             # tied to project beat grid
    'speed': 1.0,                     # runtime speed multiplier
    'crossfadeDuration': float,       # seconds fade between steps
    'smoothesFixtureMovements': False,
    'usesConstantFixtureMovementVelocity': False,
    'repeatCount': int,               # 0 = infinite loop, 1 = play once
    'beatControlled': False,          # link to project BPM? (experimental)
    'beatOffset': 0,
    'freezesAtEnd': False,            # hold last step when repeatCount exhausted?
    '$class': UID(),
}
```

### Timing maths

For a 2-step ping-pong (autoreverses=True, 2 children):
- Cycle time = `2 * (hold + crossfade)` — covers A→B→A

For a 2-step no-reverse (autoreverses=False, 2 children):
- Same: cycle time = `2 * (hold + crossfade)` (loops from last back to first)

For an N-step no-reverse, autoreverses=False:
- Cycle time = `N * (hold + crossfade)`

### Beat-sync example at 127 BPM

```python
BEAT = 60.0 / 127      # 0.4724s per beat
# For flash every beat using 2 children: cycle = 1 beat = 0.4724s
# hold + crossfade = 0.4724 / 2 = 0.2362s per step
# e.g. hold=0.1, crossfade=0.136
```

---

`crossfadeDuration: 0.0` is a valid **hard cut** (chases, bursts, strobes-by-sequence); holds down
to ~0.06 s ran fine. `smoothesFixtureMovements` only matters when steps carry pan/tilt.

## LXControlPanel

The container for the on-screen button grid.

**Class chain:** `['LXControlPanel', 'NSObject']` (confirm with your source)

```python
{
    'name': UID(),       # -> NSMutableString
    'UUID': UID(),       # -> NSUUID
    'items': UID(),      # -> NSArray of LXCpanButton + LXTextCanvasItem + LXCpanFrame UIDs
    'fadeDuration': 0.3, # default fade when no cue specifies one
    '$class': UID(),
}
```

**`items` is an NSArray (immutable) — not NSMutableArray.** This was a v1 bug I had to fix.

---

## LXCpanButton

A clickable button on the control panel.

**Class chain:** `['LXCpanButton', 'NSObject']` (confirm with your source)

```python
{
    'cue': UID(),                     # -> LXCue
    'rect': UID(),                    # -> RAW STRING '{{x, y}, {w, h}}' (NOT NSString!)
    'type': 0,                        # button type (0 = standard)
    'behavior': 0,                    # 0 = latch, 1 = momentary
    'vertical': False,                # text orientation
    'titleAlignment': 0,              # 0 = centre
    'titleUnderlineStyle': 0,
    'clusterRequiresSelection': False,  # legacy — always False
    'colorName': UID(),               # -> RAW STRING tint name ('Red', 'Orange', ...) or UID(0) = untinted
    'titleFont': UID(0),              # -> $null = use default
    '$class': UID(),
}
```

**CRITICAL GOTCHAS:**

- `rect` is a **raw plist string** (not wrapped in NSString). Use `archive['$objects'].append(rect_str)` to create, then reference by UID. If you inline the string in the button dict, Lightkey parses nothing and the button defaults to rect `{0,0,0,0}`.
- `colorName` is likewise a **raw string**. Valid AppKit colour names observed: `Red`, `Orange`, `Yellow`, `Green`, `Blue`, `Purple`, `Gray`. No `Cyan`, `Magenta`, or custom hex colours. `UID(0)` means untinted.
- There is NO `clusterID` field. Radio behaviour is done via preset-group mutual exclusion, not button-level clustering.

---

Observed `colorName` values (raw string, or `$null` for no tint): `Gray`, `Orange`, `Red`,
`Purple`, `Blue`, `Green`, `Yellow`. Tint is a display property only — changing it never affects
what the button fires.

## LXCpanFrame

A labelled bounding box around a group of buttons, with live speed/intensity/fade-time sliders.

**Class chain:** `['LXCpanFrame', 'LXCanvasItem', 'LXCanvasItemObjC', 'NSObject']`

If the source file doesn't have this class defined, you must add both `LXCpanFrame` and optionally `LXCanvasItem` class definitions yourself. These are both real Lightkey classes that exist in the app's codebase — safe to add, but only if the source doesn't already have them.

```python
{
    'name': UID(),                    # -> NSMutableString (appears as frame title)
    'UUID': UID(),                    # -> NSUUID
    'rect': UID(),                    # -> RAW STRING '{{x, y}, {w, h}}'
    'members': UID(),                 # -> NSSet of LXCpanButton UIDs inside the frame
    'showsBackButton': False,         # page nav if multi-page panel
    'showsForwardButton': False,
    'priority': int,                  # frame-level LTP override
    'titleAlignment': 0,
    'titleUnderlineStyle': 0,
    'titleFont': UID(0),              # $null = default
    'metaModifiers': UID(),           # -> NSDictionary of {speed, fadeTime, intensity}
    'metaModifierDefaults': UID(),    # -> empty NSDictionary singleton
    'activeSpeedModifiers': UID(),    # -> NSSet (empty OK)
    '$class': UID(),
}
```

### metaModifiers structure

To expose sliders to the operator:

```python
{
    'NS.keys':    [UID('fadeTime'), UID('intensity'), UID('speed')],  # RAW strings
    'NS.objects': [UID(1.0), UID(1.0), UID(1.0)],                      # RAW floats
    '$class':     UID('NSDictionary'),
}
```

Keys are stored as **raw plist strings** (not NSString). Values are **raw plist floats**. The `1.0` float can be shared — minted once, referenced three times.

**IMPORTANT:** `members` is an **NSSet**, not an NSArray. The buttons it references must ALSO appear in the parent `LXControlPanel.items` array — the frame doesn't contain them, it points at them. Buttons use absolute panel coordinates; frame rect is a bounding box overlay.

---

## LXTextCanvasItem

A plain text label placed on the panel.

**Class chain:** `['LXTextCanvasItem', 'LXGraphicalCanvasItem', 'LXCanvasItem', 'LXCanvasItemObjC', 'NSObject']`

```python
{
    'strokeWidth': 0.0,
    'autoAdjustsWidth': True,
    'strokeColor': UID(),             # -> NSColor (reuse an existing one)
    'unrotatedSize': UID(),           # -> RAW STRING '{w, h}'
    'strokeOpacity': 0.0,
    'fillOpacity': 0.0,
    'opacity': 1.0,
    'center': UID(),                  # -> RAW STRING '{cx, cy}'
    'fillColor': UID(),               # -> NSColor
    'contents': UID(),                # -> NSTextStorage (with shared attrs)
    'strokeType': 0,
    'splineKnots': UID(0),            # -> $null
    'angleCCW': 0.0,
    '$class': UID(),
}
```

**Practical tip:** don't build NSFont/NSColor from scratch for the attributes — reuse an existing `NSAttributes` dict from the source file if any `LXTextCanvasItem` already exists. (Walk for it; never hardcode the UID — Bug 15/23.) If the source has no text items, consult an Effects-Showcase-style reference file for the NSAttributes structure.

### Geometry — the part that bites

**There is no `rect`.** Position is `center` `'{cx, cy}'` and `unrotatedSize` `'{w, h}'`, both
raw plist strings. To place a box by its top-left corner, convert: `cx = x + w/2`, `cy = y + h/2`.

**The box does not scale the text.** Glyphs render at `NSAttributes → NSFont → NSSize`
regardless of `unrotatedSize`, so an undersized box lets text spill out and the next row of
buttons draws over it. Keep box height ≥ `NSSize × 1.4`; Lightkey's own labels are Helvetica
24 in `{w, 35}` boxes. Budget width at roughly 16 px/char at 24pt caps, 7.2 px/char at 13pt.

Set **`autoAdjustsWidth: False`** when you are computing your own layout — with `True`,
Lightkey re-measures the string on load and the box can grow across neighbouring items.

**Mixed font sizes** need a cloned attributes dict, not a new class. Copy the `NSFont` dict,
change `NSSize`, and rebuild the NSAttributes `NS.keys`/`NS.objects` pair around it, reusing
the same `$class` UIDs — see `pitfalls.md` Bug 24 for the exact snippet.

---

## NSTextStorage

Wraps the text string + its attributes.

**Class chain:** `['NSTextStorage', ...]` (varies)

```python
{
    'NSString':     UID(),            # -> NSMutableString with the actual text
    'NSDelegate':   UID(0),           # -> $null
    'NSAttributes': UID(),            # -> NSDictionary (font, colour, paragraph style)
    '$class':       UID(),
}
```

Reuse existing `NSAttributes` from the source file whenever possible.

---

## Bindings (MIDI, keyboard)

Lightkey stores its trigger map in `$top` under `MIDIBindingsCategory`, `keyBindingsCategory`
(and `DMXBindingsCategory`). Decoded from a real project:

```python
LXBindingsCategory {
    'identifier': 'LXMIDIBindingsCategory',
    'configurations': [LXBindingsConfiguration],      # NSArray
    'currentConfiguration': <same object as configurations[0]>,
    'liveBindingsConfiguration': $null,
}
LXBindingsConfiguration {
    'name': 'Default', 'UUID': NSUUID, 'categoryIdentifier': 'LXMIDIBindingsCategory',
    'bindings': [LXBinding],
}
LXBinding { 'UUID': NSUUID, 'trigger': LXMIDITrigger | LXKeyTrigger, 'action': LXAction }
LXMIDITrigger {
    'endpointName': 'Lightkey Input',    # Lightkey's own virtual MIDI port
    'channel': 0, 'note': 12, 'commandType': 159,     # 159 observed for note messages
    'feedbackType': 0, 'onOff': False, 'shift': 0, 'triggerType': 0,
}
LXKeyTrigger { 'triggerType': 0, 'shortcut': {'keyCode', 'modifierFlags', 'characters', 'charactersIgnoringModifiers'} }
LXAction { 'params': NSDictionary {'type': 'ToggleCue', 'activationBehavior': 0, 'cueUUID': NSUUID} }
```

* `activationBehavior`: `0` = toggle on each trigger, `1` = active while held (a momentary
  "flash" binding was `1`).
* **Bindings reference cues by `cueUUID`.** A binding whose UUID no longer matches any `LXCue`
  decodes fine and does nothing — Bug 28. `tools/inspect_project.py --midi` lists them.
* The same `LXAction` shape is used by panel buttons' `clusterRequiresSelection`-free triggers,
  so cloning a binding is: copy trigger dict with a new `note`, copy action with a new
  `cueUUID` object pointing at your cue's UUID bytes, wrap in a new `LXBinding` with a fresh
  UUID, append to `bindings`. (Not exercised in shipped output yet — the user preferred to map
  notes in the GUI.)

## Fixture profiles and capabilities

```python
LXDMXFixture {
    'shortName': 'MH_R1', 'comments': '...', 'address': 1, 'instanceCount': 1,
    'UUID': NSUUID,                       # the key used in every fpStore
    'universeUUID': NSUUID, 'universe': LXDMXUniverse,
    'fixtureProfileUUID': NSUUID,         # -> LXFixtureProfile.UUID
    'personalityIndex': 0,                # -> profile.personalities[index]
    'ignoresMasterIntensity': False, 'flexWidth': 1, 'flexHeight': 1,
    'panLowerLimit': nan, 'panUpperLimit': nan, 'tiltLowerLimit': nan, 'tiltUpperLimit': nan,
    'externalReference': '',
}
LXFixtureProfile { 'UUID', 'name', 'manufacturer', 'personalities': [LXPersonality] }
LXPersonality   { 'name', 'capabilities': [LX*Capability] }
```

Capability classes seen: `LXIntensityCapability`, `LXIntensityFineCapability`,
`LXColorComponentCapability` (one per colour channel — R, G, B, W…), `LXShutterStrobeCapability`,
`LXPanCapability` / `LXTiltCapability` (+ `Fine`), `LXPanTiltSpeedCapability`, `LXZoomCapability`,
`LXCommandCapability`, `LXModeCapability`, `LXCustomCapability`. Each carries `channel` (offset
within the personality) and `settings` — an array of `LXSetting` with a DMX range and a `params`
dict.

**Use this to answer "can fixture X do Y?" from the file** instead of guessing: a fixture can
hardware-strobe iff its personality contains `LXShutterStrobeCapability`; it has a white channel
iff it has more than three `LXColorComponentCapability` entries (then the `coolWhite` segment key
applies).

**Decoding the shutter enum:** the `LXShutterStrobeCapability.settings` entries carry
`params: {'mode': n}` with a DMX range each. The narrow range (a few DMX values, e.g. 0–6 or
240–255) is *open* — `mode 1`; the wide range is the strobe sweep — `mode 2`. That `mode` is what
Lightkey writes into a segment's `shutterState`. Hence `1 = open, 2 = strobe (+ strobeSpeed)`;
no distinct "closed" code has been observed.

## NS classes

### NSString / NSMutableString

```python
{'NS.string': 'the text', '$class': UID(...)}
```

Most Lightkey-owned text uses `NSMutableString`. Plain Python strings stored directly in `$objects` (no class wrapper) are used for rect/size/colour-name values.

### NSUUID

```python
{'NS.uuidbytes': <16 bytes>, '$class': UID(...)}
```

Generate bytes from `uuid.uuid4().bytes`.

### NSArray / NSMutableArray

```python
{'NS.objects': [UID(...), UID(...), ...], '$class': UID(...)}
```

Mutability matters. For a given field, match what the original file uses. When a field contains a stable, never-modified list (panel.items, cue.presets, preset.childNodes), it's `NSArray`. When Lightkey mutates it at runtime (some preset-group `childNodes`), it's `NSMutableArray`. When in doubt, use `NSArray`.

### NSDictionary / NSMutableDictionary

```python
{'NS.keys': [...], 'NS.objects': [...], '$class': UID(...)}
```

Same mutability caveats.

### NSSet

```python
{'NS.objects': [UID(...), ...], '$class': UID(...)}
```

Used for `LXCue.activeSpeedModifiers` and `LXCpanFrame.members`. Not interchangeable with NSArray — Lightkey type-checks these strictly.

### $null

Just `UID(0)`. Index 0 of `$objects` is always the string `'$null'`. Any optional field that's absent should point at UID(0).

---

## When adding a new class definition

Only valid when:
1. The class exists in Lightkey's real codebase (verify via another Lightkey project file, not by guessing)
2. The source file doesn't already have the definition
3. You know the full inheritance chain

The addition itself is simple:
```python
{'$classname': 'LXCpanFrame',
 '$classes': ['LXCpanFrame', 'LXCanvasItem', 'LXCanvasItemObjC', 'NSObject']}
```

Append to `$objects`, record the new UID, reference it from `$class` fields in your instances.

The reference project does NOT have `LXCpanFrame` defined. The Effects_Showcase.lightkeyproj file DOES and served as the reference for the class chain above.

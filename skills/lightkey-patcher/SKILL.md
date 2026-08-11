---
name: lightkey-patcher
description: Read, inspect, and programmatically modify macOS Lightkey lighting-control project files (.lightkeyproj). Use whenever a user mentions Lightkey, .lightkeyproj, DMX lighting automation on Mac, stage/venue/worship lighting panels, batch-generating cues or presets, or wants to build control panels, beat-synced sequences, scene cues, or modify fixture/cue/preset/panel data in a Lightkey project. Also trigger for "edit my Lightkey file", "build a control panel programmatically", "generate cues in bulk", "add beat-synced effects to lights", "my lights are showing the wrong colour", or any task involving the NSKeyedArchiver binary plist format Lightkey uses. Captures hard-won knowledge about Lightkey's internal file format that is NOT publicly documented.
---

# Lightkey Patcher

Programmatically read and modify `.lightkeyproj` files — the project format used by [Lightkey](https://lightkeyapp.com/), a macOS DMX lighting control app.

Lightkey's file format is **not publicly documented**. This captures a working understanding reverse-engineered from real project files, including the exact schemas, pitfalls, and patterns needed to generate files that Lightkey will actually open without crashing AND that render correctly in the Live panel.

## Where the files referenced below live

Paths like `docs/pitfalls.md` and `lightkey/resolve.py` are relative to the **root of this
plugin/repository** — from this skill's own directory that is `../../docs/pitfalls.md` and
`../../lightkey/resolve.py`. Read them with the Read tool as you need them; don't load all
five docs at once.

To use the Python from a working directory of your own, either add the repo root to
`sys.path` or copy `lightkey/` next to your build script:

```python
import sys; sys.path.insert(0, '<plugin-root>')
from lightkey.resolve import load, find_instances, classname
from lightkey.colour import pack_color, c8, unpack_rgb8
from lightkey.validate import Validator
```

Two CLI tools are bundled and should usually be your first move on a new file:

```bash
python3 tools/inspect_project.py  <project>.lightkeyproj   # structure, schema, groups
python3 tools/probe_colour.py     <project>.lightkeyproj   # prove the colour byte order
```

## Read these three things first

1. **Colour packing is B-low / G-mid / R-high** — blue in bits 0–15, red in bits 32–47.
   Getting this backwards programmed an entire church rig in blue while every preset was
   named "red", and it survived several versions because grey/white/amber test colours look
   identical either way. Prove it against a colour the user made in Lightkey's own picker
   before generating a palette. `fpstore-format.md` → Colour packing.
2. **From version 2 onward, modify the user's file in place.** Real users edit in Lightkey's
   GUI between versions — renaming buttons, adding their own cues, fixing rig problems.
   Regenerating the panel from your script deletes that work, and buttons you point at
   pre-existing cues don't reliably link anyway. `pitfalls.md` Bugs 21–23.
3. **Validate the written file's semantics, not just its shape.** Key-set parity catches
   decode crashes. It does not catch labels rendering under buttons, a mutex group that
   stopped rockering, or a red that comes out blue. `patterns.md` §21.

## When this documentation applies

- User wants to **batch-create** cues, presets, control-panel buttons, scenes, or sequences that would be tedious to make by hand
- User wants to **transform** an existing `.lightkeyproj` (rename fixtures, restructure presets, replace the control panel)
- User wants to **read** data out of a Lightkey project (list fixtures, extract cue timing, analyse DMX addressing)
- User needs a **beat-synced** or **scene-based** control panel for worship/performance lighting
- User wants to compose **colour banks + effect layers** that operate independently (palette selection + intensity modulation)
- User mentions any of: Lightkey, `.lightkeyproj`, NSKeyedArchiver plist modification, DMX cue generation, native Lightkey effects, fpStore

## When this documentation does NOT apply

- User wants to operate Lightkey's GUI (this documentation doesn't drive the app)
- User wants to generate MIDI or OSC from scratch (Lightkey handles those but this documentation doesn't)
- User wants DMX output directly (Lightkey does that; we only modify the project file)
- User wants live-stream RGB into Lightkey from an external source (Lightkey's MIDI/OSC bindings only trigger cues — they don't accept live colour values)

## Core workflow

Three phases per task. Follow them in order.

### Phase 1: Inspect the source file

**Always** start by inspecting the user's existing `.lightkeyproj` before modifying it.

1. Load with `plistlib.load()` (binary plist, `plistlib` handles it natively).
2. Use the resolver library at `lightkey/resolve.py` — copy into your working directory and `import resolve`.
3. **Dump the class inventory** so you know which schemas the file uses.
4. **Capture the fixture short-name → UUID mapping.** Every preset references fixtures by UUID. Address-stable mapping is the single most important reference you'll build.
5. **Check the fpStore schema.** Old schema = `umbrellaContainers` (most files in the wild). Newer schema = `containers`/`subcontainers` (Effects Showcase). Flag to user if you encounter the newer schema — this documentation targets the old one.
6. **Check whether fpStores have `effects` arrays.** If yes, the file uses native Lightkey effects. You can clone those entries verbatim into new presets (see `docs/fpstore-format.md`). You cannot *recolour* them — the colours live in an opaque `parameters` blob. Build the user's own palette as a sequence instead (`patterns.md` §22).
7. **Decode one GUI-authored saturated colour** and confirm the byte order before writing any palette.
8. **If this is not the first version, diff against what you shipped last time.** Enumerate every button with its cue name, tint and behavior, and every preset group with its mutex flag. That inventory is what tells you which buttons the user renamed, added or deleted — all of which must survive (`pitfalls.md` Bug 22). Never reuse UIDs recorded in a previous session: Lightkey compacts `$objects` on save and every UID moves (Bug 23). Re-find everything by name.

Read `docs/archive-format.md` first if you haven't worked with NSKeyedArchiver before.

### Phase 2: Clarify the user's intent

Ask before building. The space of edits is huge. Typical axes:

- **Preservation scope**: keep existing cues/panels/fixtures? Replace some? Replace all?
- **Targeting**: global (all fixtures) or per-zone (e.g. "front wash only")?
- **Interaction model**: radio groups (one active at a time) or latching (multiple)?
- **Timing**: static snapshots, beat-synced sequences, or manual-trigger only?
- **Layer composition**: colour bank + independent effects pane? Sealed song sequences? Both?
- **Live workflow**: which cues must be mutually exclusive? Which compose freely?

The best tool for eliciting these is `ask_user_input_v0` if you have it. Present 2-4 concrete options per question — avoid open-ended asking.

For a redesign of an existing panel, the question that matters most is **how much of their
current arrangement to keep** — offer "clean re-flow / keep my arrangement / full redesign"
explicitly rather than assuming. Ask it even when the user says "make it better": muscle
memory on a panel that gets run live is worth real money to them, and only they can price it.

### Designing lighting that a volunteer can run

The file being structurally correct is table stakes. What made the difference on a real
church rig:

- **Mirror the stage.** House-left and house-right at the same distance from centre get the
  same colour. Asymmetry reads as a fault, not as design. (`patterns.md` §18)
- **Vary within a family, don't repeat.** No two fixtures on identical RGB, but every fixture
  inside one colour family — the stage looks lit rather than painted. A flat two-stop wash
  gets described as "one plain colour"; a three-stop centre→edge gradient reads as depth.
- **Name looks by what they look like** ("Warm Glow", "Berry"), not by their palette internals.
  If the user renames your buttons, their names are the spec — adopt them.
- **Label every section with a plain-English hint.** "brightness movement — layers ON TOP of
  the active colour" is the difference between a volunteer using the effects row and avoiding
  it. Put the hint on the panel, not only in your handoff notes.
- **Order rows the way a human reads them** — levels ascending with Off first, sections in the
  order the service runs. "Off | 60% | 100% | 30%" is read as a bug even though it works.
- **Aim moving heads up.** Beams into the air through haze look intentional; beams across the
  room at head height look like a mistake and blind people.
- **Slow is elegant.** For anything ambient, crossfade dominates hold — 6–10 s crossfades give
  the "professional" feel; sub-second cycling reads as a cheap disco preset.

### Phase 3: Build and validate

Write a Python script that uses `plistlib` to load the archive, mutates `$objects` and `$top`, and writes back. Use the patterns from `docs/patterns.md`.

#### Stability rules (the file MUST open AND render correctly)

These were learned the hard way over many iteration cycles. Violate any of them and the file will either crash Lightkey on open or render an empty panel that looks broken.

1. **Never overwrite `top.rootPresetGroup`.** Lightkey uses the root tree to resolve panel buttons at runtime. Replacing it with an empty group makes the panel render as the empty-state placeholder. Preserve the original root; attach your new preset groups under a wrapper group prepended to its `childNodes`. See `docs/pitfalls.md` Bug 13.

2. **Names are RAW STRINGS, not `NSMutableString` wrappers.** The `name` field on every `LXCue`, `LXPreset`, `LXPresetGroup`, `LXSequence`, and `LXControlPanel` in real source files is a raw plist string (just `archive['$objects'].append(text)` — no class wrapper). Wrapping in `NSMutableString` causes Lightkey's strict decoder to silently reject the items. See `docs/pitfalls.md` Bug 14.

3. **Never hardcode UID literals for cross-referenced objects** (NSColor, NSAttributes dicts, NSFont, etc). UIDs are byte offsets into `$objects` and vary per source file. Walk for a real instance instead and reuse its UID. See `docs/pitfalls.md` Bug 15.

4. **Reuse existing class definitions** where possible. Don't mint duplicate `$classname` entries — every instance of `LXCue` should reference the same class def UID. Duplicating class defs causes NSKeyedUnarchiver to fail silently.

5. **Reuse the empty NSArray and empty NSDictionary singletons** that the source file already has. Creating fresh empty collections is harmless but introduces churn that makes diffing your output against the source much harder during validation.

6. **`activeSpeedModifiers` is `NSSet`, not `NSArray`** — even when empty. Same kind of strict-class-check bug as Bug 14.

7. **`metaModifiers` and `metaModifierDefaults` should share a singleton** — Lightkey writes them as the same empty NSDictionary UID, not two separate instances.

8. **`orphanPresetsGroup` is unique per cue** — mint a fresh `LXRootPresetGroup` for every cue you build; don't share it.

9. **Adding NEW class definitions is risky but sometimes necessary.** Only add a class def if (a) the class actually exists in Lightkey's codebase (verify by finding it in another reference project file), and (b) the instance can't be obtained any other way. Inventing class names that "sound right" silently crashes Lightkey on open.

10. **Preserve the user's existing objects byte-for-byte where you can.** On a reused `LXCpanButton`, rewrite `rect` and nothing else — never `cue`, `behavior` or `colorName`. See `docs/pitfalls.md` Bugs 21–22.

11. **Add new presets to the user's EXISTING mutually-exclusive groups**, not to parallel ones you create. Mutual exclusion ("rocker switch" behaviour) is a property of `LXPresetGroup.presetsAreMutuallyExclusive`, and it only applies within one group — a second group with the same intent does not interoperate. See `docs/pitfalls.md` Bug 25.

12. **`LXTextCanvasItem` has no `rect`** — it is `center` + `unrotatedSize`, and the text renders at its `NSFont` size regardless of the box you declare. Undersized boxes put text under your buttons. See `docs/pitfalls.md` Bug 24.

#### After every build

1. **Structurally validate.** Re-parse the output. Walk through and check:
   - No class definitions duplicated.
   - Every new `LXCue` / `LXPreset` / `LXCpanButton` / etc. has exactly the same key set as the source instance of that class.
   - `name` fields on cues/presets/groups/sequences/panel are raw strings (use the script in `docs/pitfalls.md` Bug 14).
   - Hardcoded UIDs resolve to objects of the expected class.
   - `top.rootPresetGroup` is the SAME UID as in the source (it must not be replaced).
   - Sample buttons → cues → presets → fpStores resolve cleanly.

2. **Semantically validate — assert every claim you intend to make to the user.** Structural parity says the file will open; it says nothing about whether it is usable. Re-parse the output and check geometry (zero overlap between button rects and label boxes), preservation (every source button still present with an unchanged cue), rockers (mutex flags still set, old group children still members), and colour (decode packed values back to RGB, bucket the hue, assert the family). `docs/patterns.md` §21 has the claim→assertion table. A 60-assertion validator is proportionate for a file someone runs a live service on.

3. **Never promise it will open in Lightkey.** Structural validation catches some bugs but not all. Frame output as "should work, please test and send the crash log if it doesn't."

3. **Ask for the crash log** the first time something breaks. `~/Library/Logs/DiagnosticReports/Lightkey-*.ips`. Thread 0 stack depth tells you whether it's an early decode failure (object shape wrong) or a late semantic failure (runtime logic).

Read `docs/pitfalls.md` before writing the first line of code — it's where the silent-failure bugs are documented.

## Reference material

Load these as needed — not all at once.

- **`docs/archive-format.md`** — NSKeyedArchiver, `$objects`, `$top`, UID references. **Always read this first** before touching an archive.
- **`docs/class-schemas.md`** — Exact field schemas for every Lightkey class. Consult before building any of them. **Note: as of this revision, the `name` field on `LXCue` / `LXPreset` / `LXPresetGroup` / `LXSequence` / `LXControlPanel` should be a RAW STRING UID (not an `NSMutableString` wrapper). The class-schemas doc may still show NSMutableString — defer to pitfalls.md Bug 14.**
- **`docs/fpstore-format.md`** — The inner binary plist every `LXPreset` carries. Covers `umbrellaContainers`, the native `effects` array, **colour packing (read this before any palette work)**, moving-head practicalities, the clone-and-retarget pattern.
- **`docs/patterns.md`** — Architectural patterns: radio groups, LTP layering, beat sequences, colour palettes, per-zone gradients, unified Stage Look mutex, priority stacks, momentary buttons, plus §17–§22: in-place redesign, mirror-pair gradients, collision-checked layout, composite event cues, output validation, and palette-driven flow sequences.
- **`docs/pitfalls.md`** — Specific mistakes that have crashed Lightkey on open, made the panel render empty, or silently destroyed the user's own work. **Read this BEFORE writing any code.** Bugs 1–20 are decode/render failures; Bugs 21–26 are the ones that bite when rebuilding on a file the user has been editing.

## Bundled scripts

- **`lightkey/resolve.py`** — Reusable inspection library. `find_instances(classname)`, `resolve(uid, depth=N)`. Copy into your working directory and `import resolve`.
- **`lightkey/colour.py`** — `pack_color` / `c8` / `unpack_rgb8` (corrected byte order), anchor+variation palettes, sequence-step builders.
- **`lightkey/validate.py`** — Ready-made semantic validator (`docs/patterns.md` §21). `Validator(src, out)` then `structural_parity()`, `buttons_resolve()`, `preserved_buttons()`, `no_overlap()`, `labels_fit()`, `mutex_intact([...])`, `cue_in_group()`, `hues_within()`, `depth_stops()`, `movers_aim_high()`, `report()`. Every check accumulates instead of raising, so one run shows every problem. Verified against a real 92-button panel.
- **`tools/inspect_project.py`** — CLI structure dump: object counts, fpStore schema flavour, native-effect histogram, preset groups with their mutex flags, cues, panels. `--fixtures` prints the short-name → UUID map; `--panel` details every button and label; `--classes` flags duplicate class definitions.
- **`tools/probe_colour.py`** — CLI that decodes every named colour preset under both byte orders and reports which one agrees with the preset names. Also flags presets whose stored colour contradicts their own name — those were written by a patcher with the wrong packing and render the wrong colour on real fixtures.
- **`tools/extract_effects.py`** — Pull native-effect blobs out of a reference project so they can be cloned verbatim.
- **`examples/build_dimmer_panel.py`** — Small end-to-end builder: discovers fixtures, builds intensity-only presets, wires a mutually-exclusive group, attaches under the existing root, adds a panel. Read this before writing your own builder.

## Quick-start

```python
import plistlib
from plistlib import UID

# 1. Load
with open('project.lightkeyproj', 'rb') as f:
    archive = plistlib.load(f)

objects = archive['$objects']
top = archive['$top']

# 2. Inspect — find the existing control panel
panel_uid = int(top['selectedLivePanel'])
panel = objects[panel_uid]
items_ref = panel['items']
button_uids = objects[int(items_ref)]['NS.objects']
print(f'Panel has {len(button_uids)} items')

# 3. Inspect a sample preset's fpStore
preset = objects[int(button_uids[0])]  # if it's a button
# ... navigate cue -> preset -> fpStore -> umbrellaContainers / effects

# 4. Modify — read docs/patterns.md for the patterns
# ...

# 5. Write
with open('output.lightkeyproj', 'wb') as f:
    plistlib.dump(archive, f, fmt=plistlib.FMT_BINARY)
```

For anything beyond inspection, read `docs/pitfalls.md` (the silent failures) then `docs/patterns.md` (the design patterns).

### Quick-start: revising a file the user has been editing

```python
top, objs = archive['$top'], archive['$objects']
b = Builder(archive)

def gs(u):                                   # resolve a name reference to str
    x = objs[int(u)] if isinstance(u, UID) else None
    if isinstance(x, str): return x
    if isinstance(x, dict):
        sv = x.get('NS.string')
        return gs(sv) if isinstance(sv, UID) else sv

def find_group(name):                        # by NAME — UIDs move on every save
    for i, o in enumerate(objs):
        if b._cn(o) == 'LXPresetGroup' and gs(o.get('name')) == name:
            return i

def group_append(gi, uid):                   # join the EXISTING rocker group
    cno = objs[int(objs[gi]['childNodes'])]
    cno['NS.objects'] = list(cno.get('NS.objects', [])) + [uid]

panel = objs[int(top['selectedLivePanel'])]  # keep the same panel object
for iu in objs[int(panel['items'])]['NS.objects']:
    ob = objs[int(iu)]
    if b._cn(ob) == 'LXCpanButton':
        ob['rect'] = b.raw_str(f'{{{{{x}, {y}}}, {{{w}, {h}}}}}')   # reposition ONLY
panel['items'] = b.ns_array(items)           # reused button UIDs + new label/button UIDs
```

## Critical first-time behaviours

1. **Before editing anything, dump the file's class inventory** — tells you which schemas exist.
2. **Before minting any new instance, find an existing instance of the same class** and copy its exact key set and `$classes` chain. Lightkey strictly validates shape during unarchival; extra or missing keys cause silent crashes with no error message, just `EXC_BREAKPOINT`.
3. **Confirm every UID reference in your new objects resolves to an object of the expected class.** Hardcoded UIDs from prior templates DO NOT survive across files.
4. **Never trust parsing to mean "it will work".** Parsing only verifies the binary plist is well-formed. Lightkey does additional type checks on NSKeyedUnarchiver decode AND silently rejects items whose shape doesn't match.
5. **Validate panel buttons resolve through the root tree.** Walk `top.rootPresetGroup` and confirm your new preset groups are reachable from it.
6. **Decode a saturated GUI-authored colour to confirm byte order** before generating any palette. Never test with grey, white or amber — they look the same under either order.
7. **When the user reports something wrong on the rig, work out whether it's the file or the hardware.** If Lightkey's own colour picker renders a colour correctly, the fixture profile is fine and the bug is in your packing. If one moving head aims somewhere different from its identically-configured siblings, that is physical alignment — say so rather than patching an offset into the file.

## Output discipline

- Always copy final files to a writable user-accessible location and present with `present_files` if available.
- Name outputs with version suffixes (`filename_v2.lightkeyproj`, `filename_v3.lightkeyproj`) — the user will iterate; named versions make rollback easy.
- Never overwrite the user's original input file.
- **Leave the previous panel in `livePanels` as a backup tab** and point `selectedLivePanel` at the new one. Rolling back then costs the user one click instead of a file swap.
- **Write operator notes alongside the file** — what each new section does in plain language, what was preserved, and what you can tune in one line. The person running it on Sunday is often not the person who asked for it.

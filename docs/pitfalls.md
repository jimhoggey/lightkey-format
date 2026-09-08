# Pitfalls — bugs that have crashed Lightkey

Hard-won lessons from iterating on real Lightkey files. Read this before writing your first patcher. Every bug below has cost at least one iteration cycle to diagnose.

## How Lightkey fails

Lightkey uses **NSKeyedUnarchiver with strict class validation** (Swift `decodeObject(of:forKey:)` variant). When decoding fails, you don't get a nice error message — you get `EXC_BREAKPOINT` in Thread 0, deep in Foundation. The crash log's top frames will be in `_decodeObjectBinary`, `NSKeyedUnarchiver`, and `NSCoder.decodeObject(of:forKey:)`.

The specific field that failed typically isn't in the stack trace. You have to diff your generated archive against a known-good one field by field.

## The specific bugs

### Bug 1: `activeSpeedModifiers` wrong class

**Symptom:** `EXC_BREAKPOINT` immediately on file open. Thread 0 deep in NSKeyedUnarchiver during LXCue decode.

**Cause:** I created `activeSpeedModifiers` as an `NSArray` (empty) instead of `NSSet` (empty). Swift's strict class check on `decodeObject(of: NSSet.self, forKey: "activeSpeedModifiers")` rejected it.

**Fix:** Use NSSet, even for empty collections.

```python
cue['activeSpeedModifiers'] = b.ns_set([])   # NOT b.ns_array([])
```

### Bug 2: Separate empty dicts for metaModifiers and metaModifierDefaults

**Symptom:** Same `EXC_BREAKPOINT` as Bug 1.

**Cause:** I created two separate empty NSDictionary objects for `metaModifiers` and `metaModifierDefaults`. The original file uses the same shared singleton for both.

**Fix:** Share the singleton.

```python
empty_dict = b.ns_dict([])  # returns shared singleton
cue['metaModifiers']        = empty_dict
cue['metaModifierDefaults'] = empty_dict  # same UID
```

### Bug 3: `NSMutableArray` where `NSArray` expected

**Symptom:** Crash on open.

**Cause:** I used NSMutableArray for `LXControlPanel.items`, `LXPresetGroup.childNodes`, and `top.livePanels`. The original file uses immutable NSArray.

**Fix:** Default to NSArray for any array-typed field that Lightkey doesn't actively mutate at runtime. When in doubt, inspect the source:

```python
orig_class = objects[int(orig_field)].get('$class')  # check class name
```

Only use NSMutableArray if the original does.

### Bug 4: `rect` as inline string in button dict

**Symptom:** File opens, but all buttons stack in the top-left corner at rect `{0,0,0,0}`.

**Cause:** I put the rect string inline in the button dict:

```python
# WRONG
{'rect': '{{10, 20}, {100, 36}}', ...}
```

Lightkey expects `rect` to be a **UID reference to a raw string object** in `$objects`:

```python
# CORRECT
rect_uid = archive['$objects'].append('{{10, 20}, {100, 36}}')  # raw string entry
{'rect': rect_uid, ...}
```

Because of the inline version, NSKeyedUnarchiver tried to decode a string as a UID, got nothing, and defaulted to the zero rect. No crash — just silent failure.

**Fix:** Always use `b.raw_str(rect)` (or equivalent) to add the string as a standalone UID object.

### Bug 5: `colorName` as NSString

**Symptom:** `KeyError: 'NSString' not in archive` when running the patcher (before Lightkey even sees the file).

**Cause:** Tried to mint `b.s('Red', mutable=False)` to create an NSString. But the reference project only has `NSMutableString` defined — no NSString class def at all.

More importantly: `colorName` is stored as a **raw plist string** in the original, not an NSString wrapper:

```python
{'colorName': UID_of_raw_string_'Red'}
```

**Fix:** Use `b.raw_str('Red')`, same as `rect`:

```python
color_name = b.raw_str(tint) if tint else UID(0)
```

### Bug 6: Invented `clusterID` field on buttons

**Symptom:** File opened but radio-group behaviour didn't work the way I wanted.

**Cause:** I thought radio groups were a button-level feature and added a `clusterID` field I invented. The schema doesn't have this — Lightkey ignored it.

**Fix:** Radio behaviour is at the preset-group level (`LXPresetGroup.presetsAreMutuallyExclusive = True`), not button level. See patterns.md §1.

### Bug 7: Missing `duration` field on sequence child presets

**Symptom:** Sequence appeared to decode but produced weird timing (or crashed, depending on how picky Lightkey's runtime is).

**Cause:** A normal `LXPreset` used as a child of an `LXSequence` must have an extra `duration` field (float, typically -1.0 meaning "use sequence default"). Standalone presets must NOT have this field.

**Fix:** Two distinct constructors:

```python
def mk_preset(b, name, fpstore):       # standalone
    return b.add({..., '$class': b.cls('LXPreset')})

def mk_seq_preset(b, name, fpstore):   # sequence child
    return b.add({..., 'duration': -1.0, '$class': b.cls('LXPreset')})
```

### Bug 8: Shared orphanPresetsGroup across cues

**Symptom:** Sporadic crashes or weird runtime behaviour.

**Cause:** I reused a single empty `LXRootPresetGroup` for every cue's `orphanPresetsGroup` field. Lightkey mutates this at runtime (it's where runtime-edited preset state gets stashed) and sharing causes conflicts.

**Fix:** Mint a fresh `LXRootPresetGroup` for every cue:

```python
def mk_cue(b, ...):
    return b.add({
        ...
        'orphanPresetsGroup': mk_root_preset_group(b, 'Cue Orphan Presets Group'),
        ...
    })
```

### Bug 9: Colour + intensity in same preset clobbers dimmer

**Symptom:** File opens. User hits "50% dim" — works. User hits "Red" — goes to 100% instead of staying at 50%.

**Cause:** The colour preset included `'intensity': 1.0` in its segment and `'Intensity'` in `definedFeatures`. When activated, it overrode the dim preset via LTP.

**Fix:** Separate dim presets and colour presets. Colour preset only has Color. Dim preset only has Intensity. They layer.

See patterns.md §2.

### Bug 10: Adding class definitions that Lightkey doesn't know

**Symptom:** Crash on file open, similar to Bug 1.

**Cause:** I tried adding a `$classname: 'LXClusterButton'` or similar class def for a class that doesn't exist in Lightkey's codebase. NSKeyedUnarchiver couldn't find a matching Swift class and rejected the decode.

**Fix:** Only add class defs for **real Lightkey classes**. Verify by finding the class name in another Lightkey project file. Making up class names that "sound right" is a trap.

### Bug 11: `metaModifier` keys as NSString

**Symptom:** `KeyError: 'NSString' not in archive` (same as Bug 5 family).

**Cause:** `LXCpanFrame.metaModifiers` stores keys as **raw plist strings**, not NSString. I tried to create NSString wrappers.

**Fix:** Use raw strings:

```python
mm_keys = [b.raw_str('fadeTime'), b.raw_str('intensity'), b.raw_str('speed')]
mm_vals = [b.add(1.0)] * 3  # shared float, same UID 3 times is fine
```

### Bug 12: Unresolved UID in dict keys

**Symptom:** Values coming back as opaque `UID(N)` refs when I expected resolved strings.

**Cause:** My resolver library treated NSDictionary keys/values that were `UID` refs as "already resolved" because NSDictionary gave back {UID: UID} pairs.

**Fix:** When reading any NSDictionary, always dereference both keys and values explicitly:

```python
for k_ref, v_ref in zip(dict_obj['NS.keys'], dict_obj['NS.objects']):
    k = objects[int(k_ref)]
    v = objects[int(v_ref)]
    # now k and v are the actual values
```

## Things that look scary but are actually fine

- **"The file has 4088 objects, my patched version has 5993"** — that's normal, you just added a lot of stuff. NSKeyedArchiver files routinely hit 10k+ objects.
- **"plistlib.dump is losing the key order in my cue dicts"** — Lightkey doesn't care about field order within a dict. It decodes by name.
- **"There are `_NSKeyedCoderOldStyleArray` class defs I didn't create"** — these are legacy NSKeyedArchiver internals left over from older archive migrations. Leave them alone.
- **"My file is 946KB and the original was 716KB"** — size is fine. I've seen working files up to several MB.

## General debugging strategy

If Lightkey crashes on your output:

1. **Get the crash log.** `~/Library/Logs/DiagnosticReports/Lightkey-*.ips`. Look at Thread 0 stack depth — shallow crash (1-3 frames into Foundation) means early decode failure (object shape wrong); deep crash (many frames deep, into Lightkey classes) means late semantic failure (runtime logic).

2. **Diff your output against the original, field by field.** Find an instance of the same class in the original, extract its `keys()`, compare against your new instance's `keys()`. Any discrepancy is a candidate.

3. **Check class chains.** `$classes` must match exactly. `['LXCue', 'NSObject']` is NOT the same as `['LXCue', 'LXCueObjC', 'NSObject']`.

4. **Validate one feature at a time.** If you just added scenes AND frames AND sequences and it crashes, temporarily disable all but one and build-test-iterate to find which added the bug.

5. **When in doubt, reuse singletons.** Shared empty collections are a smart thing NSKeyedArchiver does — if you create fresh empty arrays/dicts every time, you're also not a problem, but you are introducing variance that makes diffing harder.

---

## Iteration cycle 2: silent panel failures (v9 → v15)

A second round of bugs surfaced when iterating on a real production project. The hallmark of this class is that **Lightkey opens the file without crashing**, but the Live panel is silently empty or wrong colours appear — failures that look like "your code worked" until you actually try to use the output.

### Bug 13: Overwriting `top.rootPresetGroup` makes the Live panel render empty

**Symptom:** File opens. Panel shows up in the Live picker with its name, but the canvas is blank — Lightkey draws the "A fully customizable panel with buttons to control your lights during a show" empty-state copy instead of your buttons. Cue Library may also be empty.

**Cause:** I minted a fresh empty `LXRootPresetGroup` and assigned it to `archive['$top']['rootPresetGroup']` so the old v8 presets wouldn't show up in the sidebar. Lightkey uses the root tree to resolve cue references at runtime; with no reachable cues, the panel renders empty even though buttons reference valid cue UIDs in `$objects`.

**Fix:** Never overwrite `rootPresetGroup`. Preserve the original tree. To organise new content, mint a single wrapper `LXPresetGroup` containing all your new preset groups and prepend it to the existing root's `childNodes`:

```python
root_uid = int(archive['$top']['rootPresetGroup'])
root = archive['$objects'][root_uid]
cn_obj = archive['$objects'][int(root['childNodes'])]
existing = list(cn_obj.get('NS.objects', []))

wrapper = b.add({
    'name': b.raw_str('v9 Modular Panel'),
    'UUID': b.uuid_obj(),
    'childNodes': b.ns_array(b.new_preset_groups),  # all your new groups
    'presetsAreMutuallyExclusive': False,
    '$class': b.cls('LXPresetGroup'),
})
root['childNodes'] = b.ns_array([wrapper] + existing)
```

This keeps v8 content reachable AND makes your new presets discoverable in Design view.

### Bug 14: `name` field as `NSMutableString` wrapper instead of raw string

**Symptom:** Same as Bug 13 — panel is empty in Live view, name shows correctly in the picker.

**Cause:** The class-schemas.md draft says cue/preset/group `name` fields point to `NSMutableString`. Inspection of real source files shows otherwise: every `name` in source `LXCue`, `LXPreset`, `LXPresetGroup`, `LXSequence`, and `LXControlPanel` is a **raw plist string** in `$objects` (no class wrapper). My builder wrapped them in `NSMutableString`. Lightkey's strict decoder rejected the items silently.

**Validation script:**

```python
def name_kind(objs, o):
    ref = o.get('name')
    if not isinstance(ref, UID) or int(ref) == 0: return None
    v = objs[int(ref)]
    if isinstance(v, str): return 'raw_str'
    if isinstance(v, dict):
        cref = v.get('$class')
        if isinstance(cref, UID):
            return objs[int(cref)].get('$classname')
    return '?'

# Run on the source file FIRST so you know what real Lightkey writes.
# Then assert your output uses the same kind on every new instance.
```

**Fix:** Use `b.raw_str(name)` (which does `b.add(text)` — a plain string entry) instead of `b.s(name)` (which creates a `{'NS.string': text, '$class': NSMutableString}` wrapper). Apply to every constructor: `mk_preset`, `mk_seq_preset`, `mk_preset_group`, `mk_root_preset_group`, `mk_sequence`, `mk_cue`, the `LXControlPanel`, and any wrapper preset groups you mint.

(Some name fields elsewhere — e.g. the `NSString` inside an `NSTextStorage` for a text label — ARE `NSMutableString` wrappers. The raw-string rule applies specifically to the top-level `name` field on the listed Lightkey classes.)

### Bug 15: Hardcoded UID references for NSColor / NSAttributes

**Symptom:** Same as Bug 13 — panel renders blank. Inspecting the new `LXTextCanvasItem`s shows `fillColor: UID(212) -> '{187, -1}'` (a string, not an NSColor!) or `NSAttributes: UID(3539) -> NSTextStorage` (wrong class).

**Cause:** The reference patcher had `UID_NSCOLOR_WHITE = UID(212)` and `UID_LABEL_ATTRS = UID(3539)`. Those constants happened to be correct in one file but are byte offsets in the archive — they vary per source file. In v8, UID 212 is a raw string, UID 3539 is a different class entirely.

**Fix:** Auto-detect at builder init time by walking real instances:

```python
def _find_label_color(self):
    """Return UID of the NSColor used by existing LXTextCanvasItems."""
    lx_cls = self._class_uid.get('LXTextCanvasItem')
    if lx_cls is None: return UID(0)
    for o in self.objs:
        if isinstance(o, dict) and o.get('$class') == lx_cls:
            fc = o.get('fillColor')
            if isinstance(fc, UID) and int(fc) != 0:
                return fc
    return UID(0)

def _find_label_attrs(self):
    """Return UID of the NSAttributes dict used by existing label NSTextStorages."""
    lx_cls = self._class_uid.get('LXTextCanvasItem')
    ts_cls = self._class_uid.get('NSTextStorage')
    if lx_cls is None or ts_cls is None: return UID(0)
    for o in self.objs:
        if isinstance(o, dict) and o.get('$class') == lx_cls:
            contents_ref = o.get('contents')
            if isinstance(contents_ref, UID):
                ts = self.objs[int(contents_ref)]
                if isinstance(ts, dict) and ts.get('$class') == ts_cls:
                    attrs = ts.get('NSAttributes')
                    if isinstance(attrs, UID) and int(attrs) != 0:
                        return attrs
    return UID(0)
```

General rule: **never hardcode a UID literal in your builder.** Always walk for a real instance and reuse its reference. If no real instance exists, you probably shouldn't be using that field at all.

### Bug 16: Colour-only preset with no `Intensity` is invisible

**Symptom:** User presses "Hot Lava" colour button. Stage stays whatever colour it was (or goes dark). The button highlights as active, but nothing visually changes.

**Cause:** The preset declared only `['Color']` in `definedFeatures` and set just `color` in the segment. Nothing on the cue stack was driving `Intensity`, so the fixture rendered at 0% intensity even though Color was set. Worse: any previously-active cue with `Intensity` baked in kept its visible colour, so the new colour silently lost the LTP fight.

**Fix:** A "stand-alone visible" colour preset needs both `Color` and `Intensity` declared, with intensity at 1.0:

```python
seg = {
    'color': [pack_color(r, g, b)], 'xfadeToColor': 1.0,
    'intensity': 1.0,
}
features = ['Color', 'Intensity']
if k in MOVING_HEADS:
    seg['shutterState'] = 1
    features = ['Color', 'Intensity', 'Shutter']
```

Then put any "Effects Pane" intensity-modulation cues at a HIGHER priority so they win the LTP Intensity feature when active — colour stays uncontested.

### Bug 17: Cloned reference FX silently override Colour Bank selections

**Symptom:** User presses Fire Red, stage shows blue (or some other colour that wasn't asked for). Diagnostic: Fire Red has the correct RGB data; the previous-pressed cue is still active and out-priorities Fire Red.

**Cause:** Putting reference-cloned FX presets (Color Cycle, WaterFall, Crashout, Color Effect) in their own group at a higher priority than the Colour Bank. The cloned reference fpStores bake colour-effects into the `effects` array, so they keep owning the Color feature at their higher priority even when the user thinks they've moved on.

**Fix:** Put every colour-bearing cue — Colour Bank presets, song sequences, AND colour-bearing FX — into ONE mutually exclusive `LXPresetGroup`. Mutex within the group means pressing any one deactivates all the others, so the active button on screen always matches what's on stage. See `patterns.md` §10 for the full "unified Stage Look" pattern.

### Bug 18: Per-fixture brightness varies even at intensity 1.0

**Symptom:** Colour scene looks "amateur" — some fixtures visibly dim, some bright, even though every fixture has `intensity: 1.0`.

**Cause:** Saturated RGB amplitudes determine perceived brightness regardless of the intensity multiplier. A palette stop `(0x9000, 0x0000, 0x0000)` (56% red) renders dimmer than `(0xFFFF, 0x6000, 0x0000)` (full red + orange) on the same fixture profile at the same intensity setting.

**Fix:** Anchor every palette around RGB values where the dominant channel stays at `0xFFFF`. Vary only the secondary channels for hue diversity. See `patterns.md` §11 for the "anchor + variation" colour palette pattern.

### Bug 19: Global gradient across many zones produces near-monochrome small zones

**Symptom:** A 6-fixture top bar was supposed to walk Sky Blue → Deep Blue across the bar but all 6 fixtures look identical pale blue.

**Cause:** Spreading one global gradient across 22 stage fixtures means the 6 top-bar fixtures only cover indices 0–5 of 22 — the first ~25% of the palette. All six land in the "pale sky" stop of the palette.

**Fix:** Each zone gets its OWN full sweep of the palette. Top bar of 6 fixtures walks the full palette 0→1; side vertical of 4 fixtures walks the full palette 0→1 too. See `patterns.md` §12.

### Bug 20: Effects Pane Intensity priority unintentionally clobbers sequence-step intensity

**Symptom:** Built an `ITG · Chorus` sequence where PN1 and PN2 alternate-flash on the beat. Operator has Effects Pane "Pulse Slow" active. Sequence runs but PN1/PN2 don't alternate — every fixture pulses uniformly.

**Cause:** Sequence-step preset declared `Intensity` at priority 6; Effects Pane "Pulse Slow" declared `Intensity` at priority 7. Higher priority wins LTP, so Pulse Slow overrode the per-fixture intensity intent of the sequence.

**Fix:** Sequences that depend on per-fixture intensity variation should sit ABOVE the Effects Pane priority. e.g. Stage Look=6, Effects Pane=7, Sequences=8. That way a colour palette + effects compose freely, but pressing a sequence "seals" the look — Effects Pane is still active but its Intensity loses the LTP because the sequence wins.

If you want Effects Pane to compose with sequences instead, the sequence steps would need to encode RELATIVE intensity (always declare 1.0 and use a Color-only fpStore with selective animation via fixture-level dim multipliers) — Lightkey does NOT support relative modes today, so the priority-stacking trade-off is the pragmatic answer.


---

## Iteration cycle 3: rebuilding on a file the user has been editing (v16 → v20)

These come from a long-running venue project where the owner edits the project in Lightkey's
GUI between every version and re-attaches it. That workflow is the common case for real
users, and it breaks several assumptions the earlier bugs didn't cover.

### Bug 21: Buttons wired to PRE-EXISTING cues don't link in the Live panel

**Symptom:** You build a new panel that reuses the source file's cues (`'cue': UID(existing)`).
The file opens, the panel renders, the buttons look right — but pressing several sections
does nothing. The user reports "the front wash buttons weren't linked to the presets, I had
to drag them in manually."

**Cause:** Not fully understood (Lightkey resolves button→cue bindings through some
additional runtime index built at save time), but reproduced twice: buttons pointing at cue
objects that existed before your edit silently fail to arm, while buttons pointing at cues
you created in the same write work perfectly. It is not a UID-validity problem — the
reference resolves fine when you re-parse.

**Fix — pick one, don't mix:**

* **Build fresh:** every section you put on a new panel gets a freshly-minted cue+preset,
  even if that duplicates an existing one. For native-effect cues you cannot synthesise,
  clone the source preset's `fpStore` bytes verbatim into a new `LXPreset` (see
  `fpstore-format.md` → Clone-and-Retarget), then wrap in a new `LXCue`.
* **Modify in place:** keep the user's existing `LXCpanButton` objects and only rewrite
  their `rect`. The binding never changes, so it never breaks. This is strictly safer once
  the user has customised anything — see Bug 22.

### Bug 22: Rebuilding from scratch destroys the user's own work

**Symptom:** You regenerate the panel from your own spec. The user's renamed buttons
("FX: Pulse Fast (dim B)"), their hand-made cues ("Lower backlighting to 60%"), their
momentary flag on one button, and their tint choices are all gone.

**Cause:** Treating your build script as the source of truth. After version 2 of any real
project, the user's file has diverged from your script — they add buttons, rename things,
delete what they don't like, and fix rig-specific problems in the GUI.

**Fix:** Default to **in-place modification** of the user's file for every version after the
first. Concretely:

```python
panel = objs[int(top['selectedLivePanel'])]
for iu in objs[int(panel['items'])]['NS.objects']:
    ob = objs[int(iu)]
    if cn(ob) != 'LXCpanButton':
        continue
    name = gs(objs[int(ob['cue'])].get('name'))
    sect.setdefault(classify(name), []).append((name, iu))   # keep the OBJECT
...
ob['rect'] = b.raw_str(f'{{{{{x}, {y}}}, {{{w}, {h}}}}}')     # reposition only
panel['items'] = b.ns_array(items)                            # same panel object
```

Never touch `cue`, `behavior`, `colorName` or the cue's name on a reused button, and assert
in your validator that all of them are byte-identical to the source. Add new capability
*alongside* their work, never in place of it.

Corollary: a `classify(name)` router that maps every existing button to a section should
**raise on anything it doesn't recognise**, so a user-added button can never be silently
dropped from the layout.

### Bug 23: Lightkey compacts the archive on save — cached UIDs are worthless

**Symptom:** Your v(N+1) script, run against the file the user re-saved from Lightkey, writes
presets into the wrong group, or asserts on a UID that is now a different class.

**Cause:** Lightkey rewrites `$objects` when it saves. Object count changes (one project went
6238 → 5327 objects between sessions as unreferenced objects were garbage-collected) and
every UID shifts. Group UIDs, panel UIDs and fixture UIDs from a previous run do not survive.

**Fix:** Never persist a UID between sessions. Re-derive everything by name each run:

```python
def find_group(name):
    for i, o in enumerate(objs):
        if cn(o) == 'LXPresetGroup' and gs(o.get('name')) == name:
            return i
```

Fixture **UUIDs** (the `NSUUID` values used inside fpStores) *are* stable across saves — those
are safe to cache. Uppercase them; Lightkey writes them uppercase and dict lookups are
case-sensitive.

**This can happen mid-task, not just between sessions.** In one session the source file went
from 5327 to 5374 objects *while the work was in progress*, because the user saved in Lightkey
between the inspect step and the build. Everything after that was built against a stale
layout: the output's button indices no longer lined up with the source's, and a preservation
check that had passed minutes earlier started finding a raw string where it expected a button.
Cheap insurance:

```python
import os
src_mtime = os.stat(SRC).st_mtime_ns                       # capture at load
...
assert os.stat(SRC).st_mtime_ns == src_mtime, 'source changed mid-build — re-inspect'
```

When a validator suddenly disagrees with a build that just succeeded, check the source file's
mtime before you start debugging your own logic. The fix is simply to re-run the build against
the current file — but only if you notice.

### Bug 24: Label text renders under the buttons

**Symptom:** The user says "some of the text was not clear and it was hard to see — text was
covered up by the buttons."

**Cause:** `LXTextCanvasItem` has **no `rect`**. Its geometry is `center` + `unrotatedSize`,
and the glyphs render at the size in the NSTextStorage attributes' `NSFont`/`NSSize`,
**independent of the box you declare**. Placing 24pt text in a 16–20px-tall lane and then
advancing your layout cursor by 20px puts the next row of buttons straight through the text.

**Fix:**

* Box height ≥ `fontSize × 1.4`. Real Lightkey-authored titles are Helvetica 24 in `{w, 35}`.
* For smaller helper text, **clone the existing NSFont dict with a new `NSSize`** and clone
  the NSAttributes dict around it — no new class definitions needed:
  ```python
  attrs24 = objs[int(b.text_attrs)]
  keys = [gs(k) for k in attrs24['NS.keys']]
  font13 = dict(objs[int(attrs24['NS.objects'][keys.index('NSFont')])])
  font13['NSSize'] = 13.0
  objs_list = list(attrs24['NS.objects'])
  objs_list[keys.index('NSFont')] = b.add(font13)
  hint_attrs = b.add({'NS.keys': list(attrs24['NS.keys']),
                      'NS.objects': objs_list, '$class': attrs24['$class']})
  ```
* Set `autoAdjustsWidth: False` and size the width yourself (≈16 px/char at 24pt caps,
  ≈7.2 px/char at 13pt). With `True`, Lightkey re-measures at load and the box can grow over
  neighbouring buttons.
* **Assert zero overlap from the output file**, not from your in-memory layout — parse every
  button `rect` and every label `center ± size/2` and check all pairs. See `patterns.md` §19.

### Bug 25: "Rocker switch" behaviour is a preset-group property, not a button property

**Symptom:** User asks for buttons that release each other ("if I press House 10%, the 15%
that was on should turn itself off"), and you go looking for a link/cluster field on
`LXCpanButton`. There isn't one. (`clusterRequiresSelection` is not it — see Bug 6.)

**Cause:** Mutual exclusion lives on the **`LXPresetGroup`** that owns the presets:
`presetsAreMutuallyExclusive = True`. Buttons inherit the behaviour transitively through
cue → preset → group.

**Fix:** When adding cues to an existing project, append their presets to the user's
**existing** mutex group rather than creating a parallel one:

```python
def group_append(gi, uid):
    cno = objs[int(objs[gi]['childNodes'])]
    cno['NS.objects'] = list(cno.get('NS.objects', [])) + [uid]
```

A new group with the same intent does *not* interoperate — presets in group A never release
presets in group B, so the user gets two lights on at once and reports the rocker as broken.
Validate by asserting the old child set is a subset of the new one **and** that the group
still has `presetsAreMutuallyExclusive is True`.

### Bug 26: Multi-part cues need a member in every mutex they touch

**Symptom:** A composite cue (e.g. PARTY MODE = colour cycle + mover sweep + haze) works, but
"turning it off" leaves the movers still sweeping, or the haze still running.

**Cause:** Mutex only releases presets *within the same group*. A cue whose members span
Stage Look + Movers + a loose haze preset is only released in the groups where the
replacement cue also has a member.

**Fix:** Give any composite cue an explicit exit cue with a member in **each** group it
touches — for the party example: a warm-white preset in Stage Look, a movers-off preset in
Movers, and a haze-off preset. Presets that live outside any mutex (haze here) can only be
cancelled by an explicit counter-preset, never implicitly.

## Bug 27: Python ints written where UIDs belong → panel decodes as EMPTY (and Lightkey overwrites it on save)

**Symptom:** the file opens without a crash, but the Live View shows the "A fully customizable
panel with buttons…" placeholder. If the user then saves, Lightkey writes the panel back with
**zero items** and substitutes a default "Control Panel" — the on-disk file is now genuinely
empty and the original output is gone.

**Cause:** `plistlib` will happily serialise a Python `int` inside an `NS.objects` array. That is
exactly what you get when you convert item references with `int(uid)` to use them as dict keys
(`btn_by_name[name] = int(iu)`) and later append those ints back into the array. NSKeyedUnarchiver
expects a UID (a CF `$uid` dict) for every array element; an integer makes the whole array fail to
decode, silently.

**Fix:** wrap on the way back — `new_items.append(UID(iu))` — and assert
`all(isinstance(i, UID) for i in new_items)` before writing.

**Detection:** `Validator.references_are_uids()` (now part of `structural_parity()`): every element
of every `NS.objects` / `NS.keys` array and every reference-valued key (`cue`, `items`, `presets`,
`childNodes`, `fpStore`, `contents`, `center`, `rect`, …) must be a `UID` instance. Note that
`int(x)` works on both ints and UIDs, so a validator that resolves references with `int()` will
**not** see this — it has to check the type.

**Handoff rule:** tell the user *not to save* a file that shows the placeholder; ask for it back
as-is instead. A re-saved file loses the evidence and the work.

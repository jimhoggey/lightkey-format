# lightkey-format

Unofficial documentation and Python tooling for **`.lightkeyproj`** files — the project
format used by [Lightkey](https://lightkeyapp.com/), the macOS DMX lighting control app.

The format is not publicly documented. Everything here was reverse-engineered from real
project files across many build-and-test cycles on a live venue rig, so it covers not just
the schemas but the **silent failure modes** — the mistakes that make Lightkey crash on
open, render an empty panel, or quietly ignore what you wrote.

Install it into Claude and you can just ask for what you want — *"add a colour bank to my
Lightkey project"* — and it works from hard-won knowledge instead of guessing at an
undocumented binary format.

> Unofficial and unaffiliated. Not endorsed by Lightkey or Monospace. It reads and writes
> your project files, so **keep backups** and never overwrite your only copy.

---

# Install

Two ways. Pick the one that matches how you use Claude.

## If you use Claude Code (terminal)

Run these two commands:

```bash
claude plugin marketplace add jimhoggey/lightkey-format
```

```bash
claude plugin install lightkey-patcher@lightkey-format
```

Already inside Claude Code? Use `/plugin marketplace add jimhoggey/lightkey-format` and
`/plugin install lightkey-patcher@lightkey-format` instead — same thing.

Done. Later on, `/plugin marketplace update lightkey-format` updates it and
`/plugin uninstall lightkey-patcher@lightkey-format` removes it.

## If you use the Claude web or desktop app

Upload a ZIP — no terminal needed.

1. **Download the ZIP:**
   [**lightkey-patcher-skill.zip**](https://github.com/jimhoggey/lightkey-format/releases/latest/download/lightkey-patcher-skill.zip)
2. In Claude, go to **Settings → Capabilities → Skills**
   (called **Customize → Skills** in some versions).
3. Click **Add**, choose the ZIP you just downloaded, and upload it.
4. It appears in your skills list with a toggle. Leave it switched on.

You also need **code execution enabled** in settings, because the skill runs Python.
Skills you upload are private to your account.

> ⚠️ **Don't use the green "Code → Download ZIP" button on this repo.** That archive has
> `SKILL.md` in the wrong place and Claude will reject it. Use the download link above —
> it's the same content, packaged the way Claude needs.

## After installing (either way)

Nothing to configure. Claude uses it automatically as soon as you mention Lightkey, a
`.lightkeyproj` file, or DMX lighting — you never have to invoke it by name.

<details>
<summary>Other ways to install</summary>

**As a plain skill, without the plugin system:**

```bash
git clone https://github.com/jimhoggey/lightkey-format ~/.claude/lightkey-format
mkdir -p ~/.claude/skills
ln -s ~/.claude/lightkey-format/skills/lightkey-patcher ~/.claude/skills/lightkey-patcher
```

`SKILL.md` refers to `docs/…` and `lightkey/…` relative to the repo root, which the symlink
preserves. For a project-scoped install use `.claude/skills/` inside the project instead.

**With Cursor, Copilot or another assistant:** nothing here is Claude-specific. Point it at
[`skills/lightkey-patcher/SKILL.md`](skills/lightkey-patcher/SKILL.md) as the entry point —
it's plain markdown that links onward into `docs/`. Adding `SKILL.md` and
`docs/pitfalls.md` to context is enough to avoid the expensive mistakes.

**Just the Python, no AI:** see [Quick start](#quick-start-python-only) below.

</details>

---

# Using it

## In the Claude app (web or desktop)

Claude can't reach your hard drive there, so the loop is **upload → ask → download**:

1. **Find your project file** — a single `.lightkeyproj`, wherever you saved it (often
   `~/Documents`).
2. **Duplicate it first.** ⌘D in Finder. Work on the copy; never upload your only copy.
3. **Attach the copy** to a new conversation (the 📎 button) and ask for what you want.
4. **Download the file Claude gives back**, open it in Lightkey, and test it on the rig
   before a service or show.

## In Claude Code

Just point it at the file — it can read and write your project directly, which makes it the
better choice if you're iterating on a rig across many versions.

## Things worth asking

```
What's in this Lightkey project? List my fixtures, cues and preset groups.

My reds are coming out blue on the actual lights — what's wrong?

Add a House Lights row with Off / 10 / 25 / 50 / 100%, where pressing one
turns the previous one off.

Build me a colour bank: 8 warm looks for worship, mirrored left-to-right,
and make them all release each other.

Add a section of moving-head positions — stage, ceiling, and a slow sweep.

Check this file I generated: is anything broken, and does the panel have
text hidden behind buttons?
```

A realistic first session:

```
you    [attaches BackupChurch.lightkeyproj]
       What's in this project, and are any of my colours wrong?

Claude runs tools/inspect_project.py  → 34 fixtures, 145 cues, 18 preset groups,
                                        old fpStore schema, 9 mutex groups
       runs tools/probe_colour.py     → blue-low/red-high confirmed, and flags
                                        "Col: Fire Red" as storing blue
       …explains what it found and offers to fix the mis-packed presets
```

**Two habits worth keeping.** Ask Claude to *inspect before it edits* — the tooling is built
around reading your file first, and a change made without that is a guess. And **test on the
rig**, not just in the app: a project can open perfectly and still have a button wired to
nothing. `docs/pitfalls.md` exists because all of these failures are silent.

---

# Reference

## The headline finding: colours are packed B-G-R, not R-G-B

Lightkey stores each colour as a 64-bit integer with **blue in the low bits and red in the
high bits**:

```
bits  0-15: Blue     bits 16-31: Green     bits 32-47: Red     bits 48-63: Alpha
```

```python
def pack_color(r16, g16, b16, a16=0):
    return ((b16 & 0xFFFF) | ((g16 & 0xFFFF) << 16) |
            ((r16 & 0xFFFF) << 32) | ((a16 & 0xFFFF) << 48))
```

Get this backwards and every red preset renders blue — while your code, your preset names
and your validation all look correct. It survived several release cycles on a real rig
because the obvious test colours (white, grey, amber) look identical under either byte
order. **Test with a saturated primary**, or just run the probe:

```bash
python3 tools/probe_colour.py MyProject.lightkeyproj
```

It decodes every named colour preset under both interpretations, tells you which one agrees
with what the presets are called, and flags any preset whose stored colour contradicts its
own name — those were written by a patcher with the wrong packing.

## What's here

| Path | What it is |
|---|---|
| `docs/archive-format.md` | NSKeyedArchiver basics: `$objects`, `$top`, UID references |
| `docs/class-schemas.md` | Field-by-field schemas for `LXCue`, `LXPreset`, `LXSequence`, `LXControlPanel`, `LXCpanButton`, `LXTextCanvasItem`, … |
| `docs/fpstore-format.md` | The inner binary plist each preset carries: `umbrellaContainers`, colour packing, native effects, moving heads |
| `docs/patterns.md` | 22 working recipes: radio groups, LTP layering, beat-synced sequences, mirrored gradients, collision-checked panel layout, output validation |
| `docs/pitfalls.md` | 27 documented failure modes, each with symptom → cause → fix |
| `lightkey/resolve.py` | Inspection library: `load()`, `find_instances()`, `resolve(uid, depth=N)` |
| `lightkey/colour.py` | `pack_color` / `c8` / `unpack_rgb8`, uniform-brightness palettes |
| `lightkey/validate.py` | `Validator` — semantic checks on a file you generated |
| `tools/inspect_project.py` | CLI: dump fixtures, cues, panels, groups, schema flavour |
| `tools/probe_colour.py` | CLI: prove the colour byte order against your own project |
| `tools/extract_effects.py` | Pull native-effect blobs out of a reference project for cloning |
| `tools/build_skill_zip.py` | Repackage the repo as a claude.ai skill ZIP upload |
| `examples/build_dimmer_panel.py` | End-to-end: build a working radio-group dimmer panel |
| `skills/lightkey-patcher/SKILL.md` | Entry point when used as a Claude skill or plugin |
| `.claude-plugin/` | Plugin + marketplace manifests |

## Quick start (Python only)

```bash
git clone https://github.com/jimhoggey/lightkey-format
cd lightkey-format
python3 tools/inspect_project.py ~/Documents/MyProject.lightkeyproj
```

No dependencies — `plistlib` is in the standard library. Python 3.9+.

```python
from lightkey.resolve import load, find_instances, classname

data, objects = load('MyProject.lightkeyproj')
for uid in find_instances(objects, 'LXCue'):
    print(objects[uid].get('priority'))
```

## Writing to a project file

Read [`docs/pitfalls.md`](docs/pitfalls.md) **before** you write your first line. Lightkey's
unarchiver is strict and fails silently: a preset whose dict has one extra key, or a name
wrapped in `NSMutableString` instead of stored as a raw string, is dropped without an error
message. The short version:

1. Never overwrite `top.rootPresetGroup` — the Live panel resolves buttons through it.
2. `name` fields are raw plist strings, not `NSMutableString` wrappers.
3. Never hardcode UID literals — UIDs are offsets into `$objects` and move on every save.
4. Reuse existing class definitions; don't mint duplicates.
5. Modify the user's objects in place where you can. Rebuilding a panel from scratch drops
   bindings and destroys hand-made edits.

Then validate what you wrote, not what you meant:

```python
from lightkey.validate import Validator

v = Validator('source.lightkeyproj', 'output.lightkeyproj')
v.structural_parity()      # class defs, key sets, raw-string names, root untouched
v.buttons_resolve()        # every button -> cue -> preset -> fpStore
v.preserved_buttons()      # source buttons kept, bindings unchanged
v.no_overlap()             # no label rendering underneath a button
v.mutex_intact(['Colour Bank'])
v.hues_within('Fire', {'red', 'orange'})   # catches a byte-order regression
v.report()
```

## Scope

Covers the **older fpStore schema** (`umbrellaContainers`), which is what almost every file
in the wild uses. The newer `containers`/`subcontainers` schema seen in Lightkey's own
Effects Showcase is only partially mapped — contributions very welcome.

Native effects (WaterFall, Color Cycle, …) keep their parameters in an opaque blob. You can
clone them verbatim onto other fixtures, but you cannot recolour them; build your own
palette as a sequence instead (`docs/patterns.md` §22).

## Contributing

Different rigs surface different corners of the format. If you find a class this doesn't
document, a schema variant, or a new way to make Lightkey fail quietly, please open an issue
or PR — see [CONTRIBUTING.md](CONTRIBUTING.md). Please don't attach project files containing
real venue data; a minimal reproduction is more useful anyway.

## License

MIT — see [LICENSE](LICENSE).

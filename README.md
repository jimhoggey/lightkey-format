# lightkey-format

Unofficial documentation and Python tooling for **`.lightkeyproj`** files — the project
format used by [Lightkey](https://lightkeyapp.com/), the macOS DMX lighting control app.

The format is not publicly documented. Everything here was reverse-engineered from real
project files across many build-and-test cycles on a live venue rig, so it covers not just
the schemas but the **silent failure modes** — the mistakes that make Lightkey crash on
open, render an empty panel, or quietly ignore what you wrote.

> Unofficial and unaffiliated. Not endorsed by Lightkey or Monospace. It reads and writes
> your project files, so **keep backups** and never overwrite your only copy.

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

It decodes every named colour preset under both interpretations and tells you which one
agrees with what the presets are called.

## What's here

| Path | What it is |
|---|---|
| `docs/archive-format.md` | NSKeyedArchiver basics: `$objects`, `$top`, UID references |
| `docs/class-schemas.md` | Field-by-field schemas for `LXCue`, `LXPreset`, `LXSequence`, `LXControlPanel`, `LXCpanButton`, `LXTextCanvasItem`, … |
| `docs/fpstore-format.md` | The inner binary plist each preset carries: `umbrellaContainers`, colour packing, native effects, moving heads |
| `docs/patterns.md` | 22 working recipes: radio groups, LTP layering, beat-synced sequences, mirrored gradients, collision-checked panel layout, output validation |
| `docs/pitfalls.md` | 26 documented failure modes, each with symptom → cause → fix |
| `lightkey/resolve.py` | Inspection library: `load()`, `find_instances()`, `resolve(uid, depth=N)` |
| `lightkey/colour.py` | `pack_color` / `c8` / `unpack_rgb8`, uniform-brightness palettes |
| `lightkey/validate.py` | `Validator` — semantic checks on a file you generated |
| `tools/inspect_project.py` | CLI: dump fixtures, cues, panels, groups, schema flavour |
| `tools/probe_colour.py` | CLI: prove the colour byte order against your own project |
| `tools/extract_effects.py` | Pull native-effect blobs out of a reference project for cloning |
| `examples/build_dimmer_panel.py` | End-to-end: build a working radio-group dimmer panel |
| `skills/lightkey-patcher/SKILL.md` | Entry point when used as a Claude Code skill or plugin |
| `.claude-plugin/` | Plugin + marketplace manifests (see [Use it with Claude Code](#use-it-with-claude-code)) |

## Use it with Claude Code

This repo is also a **Claude Code plugin**. Installing it gives Claude the whole
knowledge base — every schema, all 26 documented failure modes, the patterns, and the
bundled Python — so you can just say *"add a colour bank to my Lightkey project"* and it
works from hard-won knowledge instead of guessing at an undocumented binary format.

### Install as a plugin (recommended)

In Claude Code:

```
/plugin marketplace add jimhoggey/lightkey-format
/plugin install lightkey-patcher@lightkey-format
```

Or from your shell:

```bash
claude plugin marketplace add jimhoggey/lightkey-format
claude plugin install lightkey-patcher@lightkey-format
```

That's it — the skill activates automatically whenever you mention Lightkey, a
`.lightkeyproj` file, or DMX lighting on macOS. It costs ~200 tokens of always-on context
and loads the detailed references only when it actually fires.

The installed plugin includes `docs/`, `lightkey/`, `tools/` and `examples/`, so Claude can
read the reference material and run the bundled tools directly:

```
> my Lightkey reds are coming out blue
      -> runs tools/probe_colour.py, finds the mis-packed presets, explains the byte order

> build me a 5-step dimmer row for the front wash
      -> reads docs/pitfalls.md, writes a builder, validates the output with lightkey/validate.py
```

Update later with `/plugin marketplace update lightkey-format`, and remove it with
`/plugin uninstall lightkey-patcher@lightkey-format`.

### Install as a plain skill (no plugin system)

If you'd rather not use the plugin system, clone the repo and point a skill at it:

```bash
git clone https://github.com/jimhoggey/lightkey-format ~/.claude/lightkey-format
mkdir -p ~/.claude/skills
ln -s ~/.claude/lightkey-format/skills/lightkey-patcher ~/.claude/skills/lightkey-patcher
```

The skill's `SKILL.md` refers to `docs/…` and `lightkey/…` relative to the repo root, which
the symlink preserves. For a project-scoped install, use `.claude/skills/` inside the
project instead of `~/.claude/skills/`.

### Use it with other AI coding tools

There's nothing Claude-specific about the content. Point any assistant at
[`skills/lightkey-patcher/SKILL.md`](skills/lightkey-patcher/SKILL.md) as its entry point —
it's a plain markdown briefing that links onward into `docs/`. For Cursor, Copilot or
similar, adding `SKILL.md` and `docs/pitfalls.md` to context is enough to avoid the
expensive mistakes.

## Quick start (no AI involved)

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

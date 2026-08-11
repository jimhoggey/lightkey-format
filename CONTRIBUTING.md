# Contributing

This documents a closed, undocumented format. Every rig exercises different corners of
it, so field reports are the most valuable contribution.

## Especially wanted

- **The newer fpStore schema** (`containers` / `subcontainers`). Only partially mapped.
  If your project uses it, `tools/inspect_project.py` will say so — a dump of one preset's
  decoded fpStore would help a lot.
- **Classes we don't document.** Run `tools/inspect_project.py --classes` and open an issue
  if you see an `LX*` class missing from `docs/class-schemas.md`.
- **New silent failures.** If Lightkey opened your generated file but something didn't work,
  that's a `docs/pitfalls.md` entry: symptom, cause, fix.
- **Fixture-profile findings.** Shutter values, colour-mixing behaviour, pan/tilt ranges for
  fixture types beyond the ones covered.

## Please don't attach real project files

They embed your venue's fixture layout and addressing. Post the decoded fragment that
matters, or build a minimal reproduction with one or two dummy fixtures. `.lightkeyproj`
is gitignored here for that reason.

## Before opening a PR

```bash
python3 -m py_compile lightkey/*.py tools/*.py examples/*.py
python3 tools/inspect_project.py <a project you own>
python3 tools/probe_colour.py <a project you own>
```

State which Lightkey version produced the file you tested against — the format can change
between releases, and a finding that only holds for one version is still worth documenting
as long as it says so.

## Style

No dependencies beyond the standard library. Documentation over cleverness: every claim in
`docs/` should be something you actually observed, and it's fine (encouraged) to say what
you're unsure about.

## The Claude Code plugin

The repository root doubles as a Claude Code plugin (`.claude-plugin/plugin.json`) and as a
single-plugin marketplace (`.claude-plugin/marketplace.json`, `"source": "./"`). That layout
is deliberate: the plugin root is the repo root, so an installed plugin carries `docs/`,
`lightkey/`, `tools/` and `examples/` with it and there is only one copy of everything.

`skills/lightkey-patcher/SKILL.md` is the entry point. It should stay a short briefing that
points into `docs/` — put detail in the docs, not in the skill, so it stays cheap to load.
Its paths are written relative to the repo root (`docs/pitfalls.md`), which resolves for both
plugin installs and the symlinked-skill install.

If you change the manifests, validate and smoke-test the install:

```bash
claude plugin validate . --strict
claude plugin marketplace add .          # from the repo's parent directory
claude plugin install lightkey-patcher@lightkey-format
claude plugin details lightkey-patcher   # confirm the skill is discovered
```

Bump `version` in **both** `.claude-plugin/plugin.json` and the marketplace entry when
publishing changes — installed users only receive an update when the version string changes.

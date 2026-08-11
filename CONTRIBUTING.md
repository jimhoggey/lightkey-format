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

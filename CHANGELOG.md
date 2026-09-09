# Changelog

## 0.2.0 — 2026-09-08

Consolidates a second round of real-rig work (a MIDI-driven video opener sharing a file with a
hand-operated service panel).

**Corrections**
- `shutterState 2` is **strobe** (with `strobeSpeed`), not closed. How to decode the enum from a
  fixture profile's `LXShutterStrobeCapability.settings`. Off = intensity 0 + `shutterState 1`.

**New failure modes** (`docs/pitfalls.md`)
- Bug 27: a Python int written where a UID belongs parses fine and makes Lightkey decode the
  panel as empty — and re-save it empty. `Validator.references_are_uids()` (in
  `structural_parity()`) catches it.
- Bug 28: rebuilt cues get new UUIDs, silently orphaning MIDI/keyboard bindings.
- Bug 29: appending into a group that shares the empty-array singleton.
- Bug 26 refined: mutual exclusion is per preset member, not per cue.

**New patterns** (`docs/patterns.md` §23–§28): one-shot cues via finite `holdDuration`
(verified on hardware), timeline/MIDI show blocks with an EXIT cue, twin flows generated from a
static preset's stored bytes, carving into a layout the user likes, strobes and hard-cut chases,
moving-head position vocabulary.

**Schemas** (`docs/class-schemas.md`): MIDI/key bindings, `LXDMXFixture` → profile →
personality → capabilities, cue timing semantics, observed button tints.

**Tooling**: `inspect_project.py --midi` (dead bindings flagged);
`Validator.no_overlap(ignore_preexisting=True)`, `one_shot()`, `single_member_in()`,
`fixtures_dark()`. Segment-key vocabulary table in `docs/fpstore-format.md`.

**Scrub**: all examples now use generic zone names; nothing identifies a particular venue.

## 0.1.0 — first public release

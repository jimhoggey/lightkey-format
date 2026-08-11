#!/usr/bin/env python3
"""
End-to-end example: add a working "rocker switch" dimmer row to an existing project.

Demonstrates the load-bearing patterns in one readable file:
  * discovering fixtures instead of hardcoding UUIDs
  * building an fpStore (old umbrellaContainers schema)
  * raw-string names, NSSet for activeSpeedModifiers, per-cue orphanPresetsGroup
  * a mutually-exclusive LXPresetGroup so the buttons release each other
  * attaching under the EXISTING root preset group, never replacing it
  * reusing the source file's class definitions and empty-collection singletons

Usage:
    python3 examples/build_dimmer_panel.py input.lightkeyproj output.lightkeyproj

Then open the output in Lightkey. The new panel is selected on launch; your original
panels are kept as extra tabs. Read docs/pitfalls.md before adapting this.
"""
import os
import plistlib
import sys
import uuid as _uuid
from plistlib import UID

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from lightkey.resolve import classname, find_instances, load  # noqa: E402

UID_NULL = UID(0)
LEVELS = [('Off', 0.0), ('25%', 0.25), ('50%', 0.5), ('75%', 0.75), ('100%', 1.0)]


class Builder:
    """Appends objects to an existing archive, reusing its classes and singletons."""

    def __init__(self, archive):
        self.objs = archive['$objects']
        self._cls = {o['$classname']: UID(i) for i, o in enumerate(self.objs)
                     if isinstance(o, dict) and '$classname' in o}
        self._empty_arr = self._empty_dict = None
        na, nd = self._cls.get('NSArray'), self._cls.get('NSDictionary')
        for i, o in enumerate(self.objs):
            if not isinstance(o, dict):
                continue
            if self._empty_arr is None and o.get('$class') == na and o.get('NS.objects') == []:
                self._empty_arr = UID(i)
            if (self._empty_dict is None and o.get('$class') == nd
                    and o.get('NS.keys') == [] and o.get('NS.objects') == []):
                self._empty_dict = UID(i)

    def add(self, obj):
        u = UID(len(self.objs))
        self.objs.append(obj)
        return u

    def cls(self, name):
        if name not in self._cls:
            raise SystemExit(f'class {name!r} not in this project — see pitfalls.md Bug 10')
        return self._cls[name]

    def raw_str(self, text):
        """Names are RAW plist strings. Wrapping them in NSMutableString makes
        Lightkey silently drop the object (pitfalls.md Bug 14)."""
        return self.add(text)

    def uuid(self):
        return self.add({'NS.uuidbytes': _uuid.uuid4().bytes, '$class': self.cls('NSUUID')})

    def array(self, uids):
        uids = list(uids)
        if not uids and self._empty_arr is not None:
            return self._empty_arr
        return self.add({'NS.objects': uids, '$class': self.cls('NSArray')})

    def empty_dict(self):
        if self._empty_dict is None:
            self._empty_dict = self.add({'NS.keys': [], 'NS.objects': [],
                                         '$class': self.cls('NSDictionary')})
        return self._empty_dict

    def nsset(self, uids):
        return self.add({'NS.objects': list(uids), '$class': self.cls('NSSet')})


def fp_intensity(fixture_uuids, level):
    """Intensity-only fpStore: touches the dimmer and nothing else, so colour
    presets can compose with it freely (docs/patterns.md §2)."""
    umbrella = {u: {'definedFeatures': ['Intensity'],
                    'fixtureContainer': {},
                    'segmentContainers': [{'intensity': float(level)}]}
                for u in fixture_uuids}
    return plistlib.dumps({'isMutable': False, 'umbrellaContainers': umbrella},
                          fmt=plistlib.FMT_BINARY)


def mk_preset(b, name, fp_bytes):
    return b.add({'name': b.raw_str(name), 'UUID': b.uuid(), 'active': False,
                  'childNodes': b.array([]), 'fpStore': b.add(fp_bytes),
                  '$class': b.cls('LXPreset')})


def mk_cue(b, name, presets, priority=4):
    empty = b.empty_dict()
    orphans = b.add({'name': b.raw_str('Cue Orphan Presets Group'), 'UUID': b.uuid(),
                     'childNodes': b.array([]), 'presetsAreMutuallyExclusive': False,
                     '$class': b.cls('LXRootPresetGroup')})   # unique per cue (Bug 8)
    return b.add({'name': b.raw_str(name), 'UUID': b.uuid(), 'active': False,
                  'activateAtStartup': False, 'activateAtShutdown': False,
                  'excludeFromLiveTriggers': False, 'requiresUnlockedApp': False,
                  'fadeInDuration': 1.0, 'fadeOutDuration': 1.0, 'fadeDuration': 0.5,
                  'holdDuration': -1.0, 'priority': int(priority), 'intensity': 1.0,
                  'presets': b.array(presets), 'orphanPresetsGroup': orphans,
                  'metaModifiers': empty, 'metaModifierDefaults': empty,  # shared (Bug 2)
                  'activeSpeedModifiers': b.nsset([]),                    # NSSet (Bug 1)
                  'intensityFeatures': UID_NULL, '$class': b.cls('LXCue')})


def mk_button(b, cue, x, y, w, h):
    return b.add({'cue': cue, 'rect': b.raw_str(f'{{{{{x}, {y}}}, {{{w}, {h}}}}}'),
                  'type': 0, 'behavior': 0, 'vertical': False, 'titleAlignment': 0,
                  'titleUnderlineStyle': 0, 'clusterRequiresSelection': False,
                  'colorName': UID_NULL, 'titleFont': UID_NULL,
                  '$class': b.cls('LXCpanButton')})


def fixture_uuids(objs, limit=None):
    """Discover fixture UUIDs from the project — never hardcode them (Bug 23)."""
    found = []
    for u in find_instances(objs, 'LXDMXFixture'):
        for v in objs[u].values():
            if isinstance(v, UID):
                cand = objs[int(v)]
                if isinstance(cand, dict) and 'NS.uuidbytes' in cand:
                    found.append(str(_uuid.UUID(bytes=cand['NS.uuidbytes'])).upper())
                    break
    return found[:limit] if limit else found


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, out = sys.argv[1], sys.argv[2]
    if os.path.abspath(src) == os.path.abspath(out):
        sys.exit('refusing to overwrite the input file')

    with open(src, 'rb') as f:
        archive = plistlib.load(f)
    top, objs = archive['$top'], archive['$objects']
    before = len(objs)
    b = Builder(archive)

    fixtures = fixture_uuids(objs)
    if not fixtures:
        sys.exit('no LXDMXFixture objects found — is this a Lightkey project?')
    print(f'{len(fixtures)} fixtures found; building a {len(LEVELS)}-step dimmer row')

    presets, buttons = [], []
    for i, (label, level) in enumerate(LEVELS):
        p = mk_preset(b, f'Dim {label}', fp_intensity(fixtures, level))
        presets.append(p)
        buttons.append(mk_button(b, mk_cue(b, f'All: {label}', [p]),
                                 16 + i * 96, 24, 90, 40))

    # Mutual exclusion — this is what makes the buttons behave like a rocker switch.
    group = b.add({'name': b.raw_str('Example Dimmer'), 'UUID': b.uuid(),
                   'childNodes': b.array(presets),
                   'presetsAreMutuallyExclusive': True,
                   '$class': b.cls('LXPresetGroup')})

    # Attach under the EXISTING root. Replacing top.rootPresetGroup makes the Live
    # panel render empty (Bug 13).
    root = objs[int(top['rootPresetGroup'])]
    root_children = objs[int(root['childNodes'])]
    root_children['NS.objects'] = [group] + list(root_children.get('NS.objects', []))

    panel = b.add({'name': b.raw_str('Example Dimmer Panel'), 'UUID': b.uuid(),
                   'items': b.array(buttons), 'fadeDuration': 0.3,
                   '$class': b.cls('LXControlPanel')})
    top['livePanels'] = b.array([panel] + list(objs[int(top['livePanels'])]['NS.objects']))
    top['selectedLivePanel'] = panel

    with open(out, 'wb') as f:
        plistlib.dump(archive, f, fmt=plistlib.FMT_BINARY)
    print(f'wrote {out}  ({before} -> {len(objs)} objects)')
    print('Now validate it:  python3 -c "from lightkey.validate import Validator; '
          f"v=Validator('{src}','{out}'); v.structural_parity(); v.buttons_resolve(); v.report()\"")


if __name__ == '__main__':
    main()

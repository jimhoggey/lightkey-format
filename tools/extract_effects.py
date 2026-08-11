"""
Extract native Lightkey effect templates from a reference .lightkeyproj.

Background: Lightkey's "Effects" feature (pulse, multi-colour blend, waterfall
chase, etc.) is stored as a `parameters` binary blob inside `fpStore['effects']`.
The blob is opaque — you can't synthesise it. But you CAN clone effect entries
from a user-curated reference file and re-target their `extent` to a different
fixture set.

This script does the extraction half. Usage:

    python extract_effects.py reference.lightkeyproj templates.pkl

The pickle stores two collections:

    {
      'preset_full_fpstores': {preset_name: [fp_bytes, ...]},
      'intensity_effects':    [(preset_name, effect_idx, effect_dict), ...],
      'colour_effects':       [(preset_name, effect_idx, effect_dict), ...],
      'pantilt_effects':      [(preset_name, effect_idx, effect_dict), ...],
    }

In your patcher, use the relevant collection:

    import copy, pickle, plistlib
    with open('templates.pkl', 'rb') as f:
        TPL = pickle.load(f)

    def find_intensity_effect(name, idx):
        for n, i, eff in TPL['intensity_effects']:
            if n == name and i == idx:
                return copy.deepcopy(eff)
        raise KeyError(f'{name}#{idx}')

    def fp_with_intensity_effect(target_keys, ref_name, ref_idx, baseline=1.0):
        eff = find_intensity_effect(ref_name, ref_idx)
        eff['extent'] = {FIX_UUID[k]: {'all': {}} for k in target_keys}
        umbrella = {...}  # baseline intensity per fixture
        return plistlib.dumps({'isMutable': False,
                               'umbrellaContainers': umbrella,
                               'effects': [eff]},
                              fmt=plistlib.FMT_BINARY)

See docs/fpstore-format.md for the full clone-and-retarget pattern.
"""

import pickle
import plistlib
import sys
from collections import defaultdict
from pathlib import Path
from plistlib import UID


def load_archive(path):
    """Load a .lightkeyproj and return (data, $objects)."""
    with open(path, 'rb') as f:
        d = plistlib.load(f)
    return d, d['$objects']


def find_instances(objs, classname):
    """Return UIDs of all instances of the given class."""
    target = None
    for i, o in enumerate(objs):
        if isinstance(o, dict) and o.get('$classname') == classname:
            target = UID(i)
            break
    if target is None:
        return []
    return [i for i, o in enumerate(objs)
            if isinstance(o, dict) and o.get('$class') == target]


def getstr(objs, ref):
    """Resolve a UID to its string value (handles raw strings and
    NSString/NSMutableString wrappers)."""
    if not isinstance(ref, UID):
        return None
    v = objs[int(ref)]
    if isinstance(v, str):
        return v
    if isinstance(v, dict) and 'NS.string' in v:
        return v['NS.string']
    return None


def extract(ref_path):
    """Walk the reference file, save every preset's full fpStore + group its
    individual effect entries by feature."""
    data, objs = load_archive(ref_path)

    full_fpstores = defaultdict(list)
    intensity_effects = []
    colour_effects = []
    pantilt_effects = []

    for u in find_instances(objs, 'LXPreset'):
        p = objs[u]
        name = getstr(objs, p.get('name'))
        if not name:
            continue
        fp_ref = p.get('fpStore')
        if not isinstance(fp_ref, UID):
            continue
        fp_bytes = objs[int(fp_ref)]
        if not isinstance(fp_bytes, bytes):
            continue

        full_fpstores[name].append(fp_bytes)

        try:
            fp = plistlib.loads(fp_bytes)
        except Exception:
            continue
        for i, eff in enumerate(fp.get('effects', [])):
            feature = eff.get('feature')
            entry = (name, i, eff)
            if feature == 'Intensity':
                intensity_effects.append(entry)
            elif feature == 'Color':
                colour_effects.append(entry)
            elif feature == 'PanTilt':
                pantilt_effects.append(entry)

    return {
        'preset_full_fpstores': dict(full_fpstores),
        'intensity_effects': intensity_effects,
        'colour_effects': colour_effects,
        'pantilt_effects': pantilt_effects,
    }


def summarise(tpl):
    """Print what was extracted."""
    print(f"  Presets with fpStores:   {len(tpl['preset_full_fpstores'])}")
    print(f"  Intensity effects:       {len(tpl['intensity_effects'])}")
    print(f"  Colour effects:          {len(tpl['colour_effects'])}")
    print(f"  PanTilt effects:         {len(tpl['pantilt_effects'])}")
    if tpl['intensity_effects']:
        print()
        print("  Intensity effect inventory:")
        print(f"  {'preset':<40} {'#':<3} {'class':<5} {'params':<7} {'pixelOrder':<10}")
        print('  ' + '-' * 75)
        for name, idx, eff in tpl['intensity_effects'][:40]:
            params_len = len(eff.get('parameters', b''))
            ptype = eff.get('pixelOrder', {}).get('type')
            print(f"  {name[:38]:<40} {idx:<3} "
                  f"{eff.get('effectClass'):<5} {params_len:<7} {ptype:<10}")
        if len(tpl['intensity_effects']) > 40:
            print(f"  ... and {len(tpl['intensity_effects']) - 40} more")


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        print('usage: extract_effects.py <reference.lightkeyproj> <output.pkl>')
        sys.exit(1)

    ref_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])

    print(f'Reading  {ref_path}')
    tpl = extract(ref_path)
    summarise(tpl)

    print()
    print(f'Writing  {out_path}')
    with open(out_path, 'wb') as f:
        pickle.dump(tpl, f)
    print(f'  {out_path.stat().st_size / 1024:.1f} KB')


if __name__ == '__main__':
    main()

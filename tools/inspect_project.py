#!/usr/bin/env python3
"""
Dump the structure of a .lightkeyproj file: schema flavour, fixtures, preset groups,
cues, sequences and control panels.

Run this first, every time, before writing anything. It answers the questions that
determine how you must build: which fpStore schema the file uses, whether it relies on
native effects, what the fixture UUID map is, and which preset groups are mutually
exclusive (Lightkey's "rocker switch" behaviour).

Usage:
    python3 tools/inspect_project.py MyProject.lightkeyproj
    python3 tools/inspect_project.py MyProject.lightkeyproj --fixtures --panel
    python3 tools/inspect_project.py MyProject.lightkeyproj --classes
"""
import argparse
import os
import plistlib
import re
import sys
from collections import Counter
from plistlib import UID

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from lightkey.resolve import load, classname, find_instances  # noqa: E402


def getstr(objs, ref):
    if not isinstance(ref, UID):
        return None
    v = objs[int(ref)]
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        s = v.get('NS.string')
        return getstr(objs, s) if isinstance(s, UID) else s
    return None


def section(title):
    print(f'\n=== {title} ===')


def show_overview(data, objs):
    section('OVERVIEW')
    print(f'objects in archive : {len(objs)}')
    print(f'$top keys          : {", ".join(sorted(data["$top"].keys()))}')
    counts = Counter(classname(objs, o) for o in objs if isinstance(o, dict))
    counts.pop(None, None)
    interesting = ['LXDMXFixture', 'LXCue', 'LXPreset', 'LXSequence', 'LXPresetGroup',
                   'LXControlPanel', 'LXCpanButton', 'LXTextCanvasItem']
    for c in interesting:
        if counts.get(c):
            print(f'{c:<19}: {counts[c]}')
    other = {k: v for k, v in counts.items() if k not in interesting and k.startswith('LX')}
    if other:
        print('other LX classes   :', ', '.join(f'{k}({v})' for k, v in sorted(other.items())))


def show_schema(objs):
    """Which fpStore schema, and are native effects in use?"""
    section('fpStore SCHEMA')
    old = new = effects = total = 0
    effect_classes = Counter()
    for u in find_instances(objs, 'LXPreset'):
        ref = objs[u].get('fpStore')
        if not isinstance(ref, UID) or not isinstance(objs[int(ref)], bytes):
            continue
        try:
            fp = plistlib.loads(objs[int(ref)])
        except Exception:
            continue
        total += 1
        if 'umbrellaContainers' in fp:
            old += 1
        if 'containers' in fp:
            new += 1
        for eff in fp.get('effects') or []:
            effects += 1
            if isinstance(eff, dict):
                effect_classes[eff.get('effectClass')] += 1
    print(f'presets with an fpStore : {total}')
    print(f'  old schema (umbrellaContainers) : {old}')
    print(f'  new schema (containers)         : {new}')
    print(f'  native effect entries           : {effects}')
    if effect_classes:
        print('  effectClass histogram           :',
              ', '.join(f'{k}×{v}' for k, v in effect_classes.most_common()))
    if new and not old:
        print('\n  NOTE: this project uses the NEWER schema, which is only partially')
        print('        mapped in docs/fpstore-format.md. Proceed carefully.')


def show_fixtures(objs):
    section('FIXTURES (short name -> UUID, DMX address)')
    rows = []
    for u in find_instances(objs, 'LXDMXFixture'):
        f = objs[u]
        name = None
        for key in ('shortName', 'name', 'label'):
            if key in f:
                name = getstr(objs, f[key]) or name
        uid_str = None
        for v in f.values():
            if isinstance(v, UID):
                cand = objs[int(v)]
                if isinstance(cand, dict) and 'NS.uuidbytes' in cand:
                    import uuid as _u
                    uid_str = str(_u.UUID(bytes=cand['NS.uuidbytes'])).upper()
                    break
        addr = f.get('startChannel', f.get('address', f.get('dmxAddress')))
        rows.append((name or '?', uid_str or '?', addr))
    for name, uid_str, addr in sorted(rows, key=lambda r: (r[2] is None, r[2], r[0])):
        print(f'  {name:<14} {uid_str}  addr={addr}')
    print(f'  ({len(rows)} fixtures — this map is what every preset references)')


def show_groups(objs):
    section('PRESET GROUPS  (mutex = rocker-switch behaviour)')
    for u in find_instances(objs, 'LXPresetGroup'):
        g = objs[u]
        children = objs[int(g['childNodes'])]['NS.objects'] if isinstance(
            g.get('childNodes'), UID) else []
        mark = 'MUTEX' if g.get('presetsAreMutuallyExclusive') else '     '
        print(f'  [{mark}] {str(getstr(objs, g.get("name"))):<34} children={len(children)}')


def show_cues(objs, limit=40):
    section('CUES')
    rows = []
    for u in find_instances(objs, 'LXCue'):
        c = objs[u]
        members = objs[int(c['presets'])]['NS.objects'] if isinstance(
            c.get('presets'), UID) else []
        kinds = Counter(classname(objs, objs[int(m)]) for m in members)
        rows.append((getstr(objs, c.get('name')), c.get('priority'),
                     c.get('fadeInDuration'), dict(kinds)))
    for name, prio, fade, kinds in rows[:limit]:
        print(f'  {str(name)[:34]:<35} prio={prio:<3} fadeIn={fade:<5} {kinds}')
    if len(rows) > limit:
        print(f'  … and {len(rows) - limit} more (use --all)')


def show_panels(data, objs):
    section('CONTROL PANELS')
    top = data['$top']
    sel = int(top['selectedLivePanel']) if 'selectedLivePanel' in top else None
    panels = []
    if 'livePanels' in top:
        panels = [int(p) for p in objs[int(top['livePanels'])]['NS.objects']]
    for pu in panels:
        p = objs[pu]
        items = objs[int(p['items'])]['NS.objects']
        kinds = Counter(classname(objs, objs[int(i)]) for i in items)
        star = ' <- selected' if pu == sel else ''
        print(f'  {str(getstr(objs, p.get("name"))):<28} items={len(items)} {dict(kinds)}{star}')


def show_panel_detail(data, objs):
    section('SELECTED PANEL — items in order')
    top = data['$top']
    if 'selectedLivePanel' not in top:
        print('  (no selected panel)')
        return
    panel = objs[int(top['selectedLivePanel'])]
    for iu in objs[int(panel['items'])]['NS.objects']:
        ob = objs[int(iu)]
        cn = classname(objs, ob)
        if cn == 'LXCpanButton':
            rect = objs[int(ob['rect'])] if isinstance(ob.get('rect'), UID) else '?'
            n = [float(x) for x in re.findall(r'-?\d+\.?\d*', str(rect))]
            box = f'({n[0]:.0f},{n[1]:.0f}) {n[2]:.0f}x{n[3]:.0f}' if len(n) == 4 else '?'
            cue = getstr(objs, objs[int(ob['cue'])].get('name')) if isinstance(
                ob.get('cue'), UID) else None
            beh = 'momentary' if ob.get('behavior') == 1 else 'latching'
            tint = getstr(objs, ob.get('colorName')) or '-'
            print(f'  BTN  {str(cue)[:30]:<31} {box:<20} {beh:<10} tint={tint}')
        elif cn == 'LXTextCanvasItem':
            ts = objs[int(ob['contents'])]
            txt = getstr(objs, ts.get('NSString'))
            centre = objs[int(ob['center'])] if isinstance(ob.get('center'), UID) else '?'
            size = objs[int(ob['unrotatedSize'])] if isinstance(
                ob.get('unrotatedSize'), UID) else '?'
            fs = None
            attrs = objs[int(ts['NSAttributes'])] if isinstance(
                ts.get('NSAttributes'), UID) else None
            if isinstance(attrs, dict) and 'NS.keys' in attrs:
                keys = [getstr(objs, k) for k in attrs['NS.keys']]
                if 'NSFont' in keys:
                    fs = objs[int(attrs['NS.objects'][keys.index('NSFont')])].get('NSSize')
            print(f'  TEXT {str(txt)[:30]:<31} centre={centre} size={size} font={fs}')


def show_classes(objs):
    section('CLASS INVENTORY ($classname definitions)')
    defs = Counter(o['$classname'] for o in objs
                   if isinstance(o, dict) and '$classname' in o)
    for name, n in sorted(defs.items()):
        flag = '  <-- DUPLICATE, will break unarchival' if n > 1 else ''
        print(f'  {name:<40} {n}{flag}')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project')
    ap.add_argument('--fixtures', action='store_true')
    ap.add_argument('--panel', action='store_true', help='detail the selected panel')
    ap.add_argument('--classes', action='store_true')
    ap.add_argument('--all', action='store_true', help='everything, no cue limit')
    args = ap.parse_args()

    data, objs = load(args.project)
    show_overview(data, objs)
    show_schema(objs)
    show_groups(objs)
    show_cues(objs, limit=10_000 if args.all else 40)
    show_panels(data, objs)
    if args.fixtures or args.all:
        show_fixtures(objs)
    if args.panel or args.all:
        show_panel_detail(data, objs)
    if args.classes or args.all:
        show_classes(objs)
    print()


if __name__ == '__main__':
    main()

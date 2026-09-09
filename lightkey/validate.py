"""
Reusable output validator for Lightkey patchers — implements patterns.md §21.

Structural parity tells you the file will DECODE. These checks tell you it will be
USABLE: buttons still bound, text not hidden under buttons, rocker groups intact,
colours actually rendering the hue you intended.

Usage:

    import validate_output as V
    v = Validator('source_v18.lightkeyproj', 'output_v20.lightkeyproj')
    v.structural_parity()          # class defs, key sets, raw names, root untouched
    v.buttons_resolve()            # every button -> cue -> preset -> fpStore
    v.preserved_buttons()          # source buttons kept, cue/behavior/tint unchanged
    v.no_overlap(ignore_preexisting=True)   # only NEW collisions fail (§26)
    v.labels_fit()                 # box height >= font size * 1.4
    v.mutex_intact(['v18 Stage Look', 'v18 Movers'])
    v.cue_in_group('Coral', 'v18 Stage Look')
    v.hues_within('PARTY MODE', {'red', 'orange', 'yellow', 'magenta', 'white'})
    v.report()                     # prints PASS/FAIL, returns True if all passed

Every method appends to self.passed / self.failed rather than raising, so one run
surfaces every problem. Add project-specific assertions with v.chk(cond, msg).
"""
import colorsys
import plistlib
import re
from collections import Counter
from plistlib import UID

from . import resolve as R


def unpack_rgb8(packed):
    """Lightkey packs B low, G mid, R high. See docs/fpstore-format.md."""
    return (((packed >> 32) & 0xFFFF) >> 8,
            ((packed >> 16) & 0xFFFF) >> 8,
            (packed & 0xFFFF) >> 8)


def hue_name(r, g, b):
    """Bucket an RGB triple into a coarse hue name for family assertions."""
    if max(r, g, b) < 16:
        return 'off'
    h, s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if s < 0.18:
        return 'white'
    d = h * 360
    for limit, name in [(18, 'red'), (48, 'orange'), (70, 'yellow'), (95, 'lime'),
                        (165, 'green'), (200, 'cyan'), (255, 'blue'), (295, 'purple'),
                        (335, 'magenta'), (361, 'red')]:
        if d < limit:
            return name
    return 'red'


def _nums(s):
    return [float(x) for x in re.findall(r'-?\d+\.?\d*', s)]


class Validator:
    def __init__(self, src_path, out_path):
        self.sA, self.oA = R.load(src_path)
        self.sB, self.oB = R.load(out_path)
        self.ORIG = len(self.oA)          # objects at/after this index are new
        self.passed, self.failed = [], []

    # ---- helpers -------------------------------------------------------
    def chk(self, cond, msg):
        (self.passed if cond else self.failed).append(msg)
        return bool(cond)

    def cn(self, o):
        return R.classname(self.oB, o)

    def gs(self, u, objs=None):
        objs = self.oB if objs is None else objs
        if not isinstance(u, UID):
            return None
        x = objs[int(u)]
        if isinstance(x, str):
            return x
        if isinstance(x, dict):
            sv = x.get('NS.string')
            return self.gs(sv, objs) if isinstance(sv, UID) else sv
        return None

    def panel(self):
        return self.oB[int(self.sB['$top']['selectedLivePanel'])]

    def items(self):
        return [int(i) for i in self.oB[int(self.panel()['items'])]['NS.objects']]

    def buttons(self):
        return [i for i in self.items() if self.cn(self.oB[i]) == 'LXCpanButton']

    def labels(self):
        return [i for i in self.items() if self.cn(self.oB[i]) == 'LXTextCanvasItem']

    def group_by(self, name):
        for i, o in enumerate(self.oB):
            if self.cn(o) == 'LXPresetGroup' and self.gs(o.get('name')) == name:
                return i
        return None

    def cue_by(self, name, new_only=False):
        start = self.ORIG if new_only else 0
        for i in range(start, len(self.oB)):
            if self.cn(self.oB[i]) == 'LXCue' and self.gs(self.oB[i].get('name')) == name:
                return i
        return None

    def btn_box(self, iu):
        n = _nums(self.oB[int(self.oB[iu]['rect'])])
        return (n[0], n[1], n[2], n[3])

    def lbl_box(self, iu):
        ob = self.oB[iu]
        cx, cy = _nums(self.oB[int(ob['center'])])
        w, h = _nums(self.oB[int(ob['unrotatedSize'])])
        return (cx - w / 2, cy - h / 2, w, h)

    def lbl_font_size(self, iu):
        ts = self.oB[int(self.oB[iu]['contents'])]
        attrs = self.oB[int(ts['NSAttributes'])]
        keys = [self.gs(k) for k in attrs['NS.keys']]
        if 'NSFont' not in keys:
            return None
        return self.oB[int(attrs['NS.objects'][keys.index('NSFont')])].get('NSSize')

    # ---- checks --------------------------------------------------------
    def structural_parity(self, classes=('LXCue', 'LXPreset', 'LXSequence',
                                         'LXCpanButton', 'LXTextCanvasItem',
                                         'NSTextStorage')):
        def cdefs(objs):
            return Counter(o['$classname'] for o in objs
                           if isinstance(o, dict) and '$classname' in o)
        self.chk(not {k: v for k, v in cdefs(self.oB).items() if v > 1},
                 'no duplicate class defs')
        self.chk(not (set(cdefs(self.oB)) - set(cdefs(self.oA))), 'no new class defs')
        self.chk(int(self.sA['$top']['rootPresetGroup']) ==
                 int(self.sB['$top']['rootPresetGroup']), 'rootPresetGroup unchanged')
        self.references_are_uids()

        def ks(o):
            return frozenset(k for k in o.keys() if k != '$class')
        for c in classes:
            us = R.find_instances(self.oA, c)
            if not us:
                continue
            ref = ks(self.oA[us[0]])
            allowed = {ref, ref | {'duration'}} if c == 'LXPreset' else {ref}
            bad = [i for i in range(self.ORIG, len(self.oB))
                   if self.cn(self.oB[i]) == c and ks(self.oB[i]) not in allowed]
            self.chk(not bad, f'{c} key-set parity ({len(bad)} bad)')
        bad = [i for i in range(self.ORIG, len(self.oB))
               if self.cn(self.oB[i]) in ('LXCue', 'LXPreset', 'LXSequence', 'LXPresetGroup')
               and isinstance(self.oB[i].get('name'), UID)
               and not isinstance(self.oB[int(self.oB[i]['name'])], str)]
        self.chk(not bad, f'new names are raw strings ({len(bad)} bad)')

    # keys whose values must be object references (UID) whenever present
    REF_KEYS = ('cue', 'rect', 'name', 'items', 'presets', 'childNodes', 'fpStore', 'contents',
                'center', 'unrotatedSize', 'colorName', 'UUID', 'trigger', 'action', 'params',
                'orphanPresetsGroup', 'metaModifiers', 'metaModifierDefaults', 'activeSpeedModifiers',
                'NSString', 'NSAttributes', 'fillColor', 'strokeColor', 'titleFont', 'livePanels',
                'selectedLivePanel', 'rootPresetGroup')

    def references_are_uids(self):
        """Bug 27 — plistlib happily writes a Python int where NSKeyedArchiver expects a UID
        (e.g. an index you converted with int() for a dict key and then appended back).
        The file still parses; Lightkey silently decodes the array as empty, shows the
        Live View placeholder, and if the user saves, REPLACES the panel with an empty
        default one. Every NS.objects / NS.keys element and every reference-valued key
        must be a UID instance."""
        bad = []
        for i, o in enumerate(self.oB):
            if not isinstance(o, dict):
                continue
            for k in ('NS.objects', 'NS.keys'):
                for j, x in enumerate(o.get(k, [])):
                    if not isinstance(x, UID):
                        bad.append((i, k, j, type(x).__name__))
            for k in self.REF_KEYS:
                if k in o and not isinstance(o[k], UID) and o[k] != '$null':
                    bad.append((i, k, type(o[k]).__name__))
        for k, x in self.sB['$top'].items():
            if k in self.REF_KEYS and not isinstance(x, UID):
                bad.append(('$top', k, type(x).__name__))
        self.chk(not bad, f'every object reference is a UID instance ({len(bad)} bad) {bad[:4]}')

    def buttons_resolve(self):
        broken = []
        for iu in self.buttons():
            cue = self.oB[iu].get('cue')
            if not isinstance(cue, UID) or self.cn(self.oB[int(cue)]) != 'LXCue':
                broken.append(('btn->cue', iu))
                continue
            for pu in self.oB[int(self.oB[int(cue)]['presets'])]['NS.objects']:
                po = self.oB[int(pu)]
                if self.cn(po) == 'LXPreset' and not isinstance(
                        self.oB[int(po['fpStore'])], bytes):
                    broken.append(('preset', int(pu)))
                elif self.cn(po) == 'LXSequence':
                    for su in self.oB[int(po['childNodes'])]['NS.objects']:
                        if self.cn(self.oB[int(su)]) != 'LXPreset':
                            broken.append(('seqstep', int(su)))
        self.chk(not broken,
                 f'all {len(self.buttons())} buttons resolve ({len(broken)} broken) {broken[:3]}')

    def preserved_buttons(self):
        """Bug 22 — the user's own buttons must survive untouched but for position."""
        panelA = self.oA[int(self.sA['$top']['selectedLivePanel'])]
        src = {}
        for i in self.oA[int(panelA['items'])]['NS.objects']:
            ob = self.oA[int(i)]
            if R.classname(self.oA, ob) == 'LXCpanButton' and isinstance(ob.get('cue'), UID):
                src[int(i)] = int(ob['cue'])
        reused = [iu for iu in self.buttons() if iu < self.ORIG]
        self.chk(len(reused) == len(src),
                 f'all {len(src)} source buttons preserved ({len(reused)} present)')
        changed = [iu for iu in reused if int(self.oB[iu]['cue']) != src.get(iu)]
        self.chk(not changed, f'reused buttons keep their cue ({len(changed)} changed)')
        meta = [iu for iu in reused
                if self.oB[iu].get('behavior') != self.oA[iu].get('behavior')
                or int(self.oB[iu].get('colorName', UID(0))) !=
                int(self.oA[iu].get('colorName', UID(0)))]
        self.chk(not meta, f'reused buttons keep behavior/tint ({len(meta)} changed)')

    def _boxes(self, objs, top):
        panel = objs[int(top['selectedLivePanel'])]
        out = []
        for iu in objs[int(panel['items'])]['NS.objects']:
            ob = objs[int(iu)]
            c = R.classname(objs, ob)
            if c == 'LXCpanButton':
                out.append(('btn', int(iu), tuple(_nums(objs[int(ob['rect'])]))))
            elif c == 'LXTextCanvasItem':
                cx, cy = _nums(objs[int(ob['center'])])
                w, h = _nums(objs[int(ob['unrotatedSize'])])
                out.append(('lbl', int(iu), (cx - w / 2, cy - h / 2, w, h)))
        return out

    @staticmethod
    def _collisions(boxes):
        hits = set()
        for a in range(len(boxes)):
            _k1, u1, (x1, y1, w1, h1) = boxes[a]
            for bidx in range(a + 1, len(boxes)):
                _k2, u2, (x2, y2, w2, h2) = boxes[bidx]
                if not (x1 >= x2 + w2 or x2 >= x1 + w1 or y1 >= y2 + h2 or y2 >= y1 + h1):
                    hits.add((min(u1, u2), max(u1, u2)))
        return hits

    def no_overlap(self, canvas_w=None, ignore_preexisting=False):
        """Bug 24 — labels and buttons must not intersect. Checked from the FILE.

        ignore_preexisting=True (patterns.md §26): GUI-made panels often have title boxes that
        extend 3-4px under the first button row. Those pairs already collide in the SOURCE and
        are the user's arrangement — only NEW collisions fail."""
        boxes = self._boxes(self.oB, self.sB['$top'])
        hits = self._collisions(boxes)
        if ignore_preexisting:
            old = self._collisions(self._boxes(self.oA, self.sA['$top']))
            kept = len(hits & old)
            hits -= old
            self.chk(not hits, f'no NEW label/button overlaps among {len(boxes)} items '
                               f'({len(hits)} new, {kept} pre-existing kept) {sorted(hits)[:3]}')
        else:
            self.chk(not hits, f'zero overlap among {len(boxes)} panel items '
                               f'({len(hits)} collisions) {sorted(hits)[:3]}')
        oob = [u for _k, u, (x, y, w, _h) in boxes
               if x < 0 or y < 0 or (canvas_w and x + w > canvas_w)]
        self.chk(not oob, f'all items on-canvas ({len(oob)} out)')

    def labels_fit(self, ratio=1.4):
        bad = []
        for iu in self.labels():
            fs = self.lbl_font_size(iu)
            h = self.lbl_box(iu)[3]
            if fs is None or h < fs * ratio:
                bad.append((iu, fs, h))
        self.chk(not bad, f'every label box fits its font ({len(bad)} too small) {bad[:3]}')

    def mutex_intact(self, group_names):
        """Bug 25 — rocker groups still mutex, and no member was dropped."""
        for name in group_names:
            gi = self.group_by(name)
            if not self.chk(gi is not None, f'{name}: group present'):
                continue
            self.chk(self.oB[gi].get('presetsAreMutuallyExclusive') is True,
                     f'{name}: still mutually exclusive')
            new = set(int(c) for c in self.oB[int(self.oB[gi]['childNodes'])]['NS.objects'])
            giA = None
            for i, o in enumerate(self.oA):
                if (R.classname(self.oA, o) == 'LXPresetGroup'
                        and self.gs(o.get('name'), self.oA) == name):
                    giA = i
                    break
            if giA is not None:
                old = set(int(c) for c in self.oA[int(self.oA[giA]['childNodes'])]['NS.objects'])
                self.chk(old <= new, f'{name}: no original members removed')

    def cue_in_group(self, cue_name, group_name):
        """A new colour cue only rockers if its preset joined the EXISTING group."""
        cu = self.cue_by(cue_name)
        gi = self.group_by(group_name)
        if not self.chk(cu is not None and gi is not None,
                        f'{cue_name} / {group_name}: both exist'):
            return
        children = set(int(c) for c in self.oB[int(self.oB[gi]['childNodes'])]['NS.objects'])
        members = [int(p) for p in self.oB[int(self.oB[cu]['presets'])]['NS.objects']]
        self.chk(any(m in children for m in members),
                 f'{cue_name} has a member in {group_name} (rockers correctly)')

    def _cue_colours(self, cue_uid):
        out = []
        for pu in self.oB[int(self.oB[cue_uid]['presets'])]['NS.objects']:
            po = self.oB[int(pu)]
            step_uids = ([int(s) for s in self.oB[int(po['childNodes'])]['NS.objects']]
                         if self.cn(po) == 'LXSequence' else [int(pu)])
            for su in step_uids:
                so = self.oB[su]
                if not isinstance(so.get('fpStore'), UID):
                    continue
                fp = plistlib.loads(self.oB[int(so['fpStore'])])
                for cont in fp.get('umbrellaContainers', {}).values():
                    for seg in cont.get('segmentContainers', []):
                        if isinstance(seg.get('color'), list):
                            out.append(unpack_rgb8(seg['color'][0]))
        return out

    def hues_within(self, cue_name, families):
        """The only check that catches a colour byte-order regression."""
        cu = self.cue_by(cue_name)
        if not self.chk(cu is not None, f'{cue_name}: cue exists'):
            return
        seen = Counter(hue_name(*c) for c in self._cue_colours(cu))
        self.chk(seen and not (set(seen) - set(families)),
                 f'{cue_name}: hues within {sorted(families)} (got {dict(seen)})')

    def depth_stops(self, cue_name, minimum=3):
        cu = self.cue_by(cue_name)
        if not self.chk(cu is not None, f'{cue_name}: cue exists'):
            return
        n = len(set(self._cue_colours(cu)))
        self.chk(n >= minimum, f'{cue_name}: {n} distinct stops (>= {minimum})')

    def movers_aim_high(self, cue_name, min_tilt=1.0, min_xfade=None):
        cu = self.cue_by(cue_name)
        if not self.chk(cu is not None, f'{cue_name}: cue exists'):
            return
        tilts, xfades = set(), set()
        for pu in self.oB[int(self.oB[cu]['presets'])]['NS.objects']:
            po = self.oB[int(pu)]
            if self.cn(po) != 'LXSequence':
                continue
            for su in self.oB[int(po['childNodes'])]['NS.objects']:
                fp = plistlib.loads(self.oB[int(self.oB[int(su)]['fpStore'])])
                for cont in fp.get('umbrellaContainers', {}).values():
                    for seg in cont.get('segmentContainers', []):
                        if 'tiltAngle' in seg:
                            tilts.add(round(seg['tiltAngle'], 3))
                            xfades.add(po.get('crossfadeDuration'))
        self.chk(tilts and all(t >= min_tilt for t in tilts),
                 f'{cue_name}: beams aim high (tilts={sorted(tilts)})')
        if min_xfade is not None:
            self.chk(xfades and min(xfades) >= min_xfade,
                     f'{cue_name}: movement is slow (xfades={sorted(xfades)})')

    # ---- show-block checks (patterns.md §23-24) --------------------------
    def one_shot(self, cue_name, max_hold=2.0, priority=None):
        """A cue meant to flash and release itself: finite hold, snap in."""
        cu = self.cue_by(cue_name)
        if not self.chk(cu is not None, f'{cue_name}: cue exists'):
            return
        c = self.oB[cu]
        ok = 0 < c.get('holdDuration', -1.0) <= max_hold and c.get('fadeInDuration') == 0.0
        if priority is not None:
            ok = ok and c.get('priority') == priority
        self.chk(ok, f'{cue_name}: one-shot (hold {c.get("holdDuration")}s, prio {c.get("priority")})')

    def single_member_in(self, cue_name, group_name):
        """Exactly ONE preset/sequence, and it is in the named mutex group (Bug 26 rule)."""
        cu, gi = self.cue_by(cue_name), self.group_by(group_name)
        if not self.chk(cu is not None and gi is not None, f'{cue_name} / {group_name}: both exist'):
            return
        members = [int(p) for p in self.oB[int(self.oB[cu]['presets'])]['NS.objects']]
        children = set(int(c) for c in self.oB[int(self.oB[gi]['childNodes'])]['NS.objects'])
        self.chk(len(members) == 1 and members[0] in children,
                 f'{cue_name}: exactly one member, in {group_name}')

    def fixtures_dark(self, cue_name, fixture_uuids):
        """The given fixtures are never lit by any preset/step of the cue (intensity <= 0)."""
        cu = self.cue_by(cue_name)
        if not self.chk(cu is not None, f'{cue_name}: cue exists'):
            return
        want = {u.upper() for u in fixture_uuids}
        lit = set()
        for pu in self.oB[int(self.oB[cu]['presets'])]['NS.objects']:
            po = self.oB[int(pu)]
            steps = ([int(x) for x in self.oB[int(po['childNodes'])]['NS.objects']]
                     if self.cn(po) == 'LXSequence' else [int(pu)])
            for su in steps:
                fp = plistlib.loads(self.oB[int(self.oB[su]['fpStore'])])
                for fu, cont in fp.get('umbrellaContainers', {}).items():
                    if fu.upper() in want and any(seg.get('intensity', 0) > 0
                                                  for seg in cont.get('segmentContainers', [])):
                        lit.add(fu.upper())
        self.chk(not lit, f'{cue_name}: protected fixtures never lit ({len(lit)} lit)')

    # ---- output --------------------------------------------------------
    def report(self):
        print('PASS:')
        for m in self.passed:
            print('  ✓', m)
        if self.failed:
            print('\nFAIL:')
            for m in self.failed:
                print('  ✗', m)
        print(f'\n{len(self.passed)} passed, {len(self.failed)} failed')
        return not self.failed

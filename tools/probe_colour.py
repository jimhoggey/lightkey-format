#!/usr/bin/env python3
"""
Prove which byte order a Lightkey project uses for packed colours.

Lightkey packs colour as a 64-bit int. This tool decodes every colour-bearing preset
in a project under BOTH interpretations — B-low (what this repo documents) and R-low
(the intuitive-but-wrong guess) — and scores each against the preset's own name.

Why bother: if you get the order backwards, every red preset renders blue while your
code, your names and your structural validation all still look correct. The failure
is invisible to everything except a real fixture. White, grey and amber decode
identically under both orders, so a casual test proves nothing.

Usage:
    python3 tools/probe_colour.py MyProject.lightkeyproj
    python3 tools/probe_colour.py MyProject.lightkeyproj --all

Exit status is 0 if the evidence supports B-low, 1 if it supports R-low, 2 if the
project has no decisive colours (rename a preset to "Red" in Lightkey and re-run).
"""
import argparse
import colorsys
import os
import plistlib
import sys
from collections import Counter
from plistlib import UID

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from lightkey.resolve import load, classname  # noqa: E402

# Preset-name keyword -> hue families that name could legitimately decode to.
# Only strongly-coloured words are listed: "warm white", "amber" and friends are
# deliberately absent because they are ambiguous under a red/blue transposition.
NAME_HUES = {
    'red': {'red'}, 'fire': {'red', 'orange'}, 'crimson': {'red'}, 'scarlet': {'red'},
    'ruby': {'red', 'magenta'}, 'blood': {'red'}, 'lava': {'red', 'orange'},
    'blue': {'blue', 'cyan'}, 'ocean': {'blue', 'cyan'}, 'sky': {'blue', 'cyan'},
    'azure': {'blue', 'cyan'}, 'navy': {'blue'}, 'sapphire': {'blue'},
    'ice': {'blue', 'cyan', 'white'}, 'arctic': {'blue', 'cyan', 'white'},
    'green': {'green', 'lime'}, 'emerald': {'green'}, 'forest': {'green'},
    'jungle': {'green', 'lime'}, 'lime': {'lime', 'green'}, 'mint': {'green', 'cyan'},
    'sage': {'green', 'lime'},
    'cyan': {'cyan'}, 'teal': {'cyan', 'green'}, 'turquoise': {'cyan'},
    'purple': {'purple', 'magenta'}, 'violet': {'purple'}, 'lavender': {'purple'},
    'royal': {'purple', 'blue'}, 'amethyst': {'purple'}, 'indigo': {'purple', 'blue'},
    'magenta': {'magenta'}, 'pink': {'magenta', 'red'}, 'rose': {'red', 'magenta'},
    'berry': {'magenta', 'red'}, 'fuchsia': {'magenta'},
    'orange': {'orange'}, 'sunset': {'orange', 'red'}, 'tangerine': {'orange'},
    'copper': {'orange', 'red'}, 'ember': {'orange', 'red'},
    'yellow': {'yellow'}, 'gold': {'yellow', 'orange'}, 'lemon': {'yellow'},
}
AMBIGUOUS = {'white', 'off', 'black', 'grey', 'gray'}


def decode(packed, order):
    """order='bgr' -> B low / R high (correct). order='rgb' -> R low / B high."""
    lo = packed & 0xFFFF
    mid = (packed >> 16) & 0xFFFF
    hi = (packed >> 32) & 0xFFFF
    r, g, b = (hi, mid, lo) if order == 'bgr' else (lo, mid, hi)
    return (r >> 8, g >> 8, b >> 8)


def hue_name(r, g, b):
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


def expected_for(name):
    low = (name or '').lower()
    if any(w in low for w in AMBIGUOUS) and not any(k in low for k in NAME_HUES):
        return None
    hits = set()
    for keyword, families in NAME_HUES.items():
        if keyword in low:
            hits |= families
    return hits or None


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


def preset_colours(objs, preset):
    """Every packed colour int in a preset's fpStore (old umbrellaContainers schema)."""
    ref = preset.get('fpStore')
    if not isinstance(ref, UID) or not isinstance(objs[int(ref)], bytes):
        return []
    try:
        fp = plistlib.loads(objs[int(ref)])
    except Exception:
        return []
    out = []
    for cont in (fp.get('umbrellaContainers') or {}).values():
        if not isinstance(cont, dict):
            continue
        for seg in cont.get('segmentContainers', []):
            c = seg.get('color')
            if isinstance(c, list) and c and isinstance(c[0], int):
                out.append(c[0])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('project', help='path to a .lightkeyproj file')
    ap.add_argument('--all', action='store_true',
                    help='list every colour preset, not just the decisive ones')
    args = ap.parse_args()

    _data, objs = load(args.project)
    rows, score = [], Counter()

    for i, o in enumerate(objs):
        if not isinstance(o, dict) or classname(objs, o) != 'LXPreset':
            continue
        name = getstr(objs, o.get('name'))
        cols = preset_colours(objs, o)
        if not cols:
            continue
        # Use the most saturated colour in the preset — the most discriminating one.
        best = max(cols, key=lambda p: max(decode(p, 'bgr')) - min(decode(p, 'bgr')))
        bgr, rgb = decode(best, 'bgr'), decode(best, 'rgb')
        h_bgr, h_rgb = hue_name(*bgr), hue_name(*rgb)
        want = expected_for(name)
        verdict = ''
        if want and h_bgr != h_rgb:
            if h_bgr in want and h_rgb not in want:
                score['bgr'] += 1
                verdict = 'B-low ✓'
            elif h_rgb in want and h_bgr not in want:
                score['rgb'] += 1
                verdict = 'R-low ✓'
            else:
                verdict = 'inconclusive'
        rows.append((name, bgr, h_bgr, rgb, h_rgb, verdict))

    if not rows:
        print('No colour-bearing presets found. If this project uses the newer '
              "'containers' fpStore schema, this tool does not read it yet.")
        return 2

    decisive = [r for r in rows if r[5].endswith('✓')]
    shown = rows if args.all else (decisive or rows[:15])
    print(f'{"preset":<28} {"B-low decode":<20} {"R-low decode":<20} verdict')
    print('-' * 84)
    for name, bgr, h_bgr, rgb, h_rgb, verdict in shown:
        print(f'{(name or "?")[:27]:<28} '
              f'{str(bgr):<13}{h_bgr:<7} {str(rgb):<13}{h_rgb:<7} {verdict}')

    print()
    total = score['bgr'] + score['rgb']
    if not total:
        print('INCONCLUSIVE — no preset name implies a specific hue.')
        print('Fix: in Lightkey, make a preset that is pure saturated red, name it '
              '"Red", save, and re-run this tool.')
        return 2

    winner = 'bgr' if score['bgr'] >= score['rgb'] else 'rgb'
    loser = 'rgb' if winner == 'bgr' else 'bgr'
    pct = 100 * score[winner] / total
    label = {'bgr': 'blue-low / red-high', 'rgb': 'red-low / blue-high'}
    print(f'RESULT: {label[winner]}  ({score[winner]}/{total} presets agree, {pct:.0f}%)')
    if winner == 'bgr':
        print('        pack_color(r,g,b) = b | (g << 16) | (r << 32)      <- use this')
    else:
        print('        This contradicts every file seen so far — please open an issue')
        print('        with your Lightkey version; it may indicate a format change.')

    # The minority is the interesting part: presets whose stored colour disagrees with
    # their own name are almost always the work of a tool that packed them backwards.
    suspects = [r for r in rows if r[5].startswith(
        'R-low' if winner == 'bgr' else 'B-low')]
    if suspects:
        print()
        print(f'⚠  {len(suspects)} preset(s) decode the OTHER way — they are named for one')
        print('   colour but store another. These were most likely written by a patcher')
        print('   using the wrong byte order, and they render the wrong colour on real')
        print('   fixtures. Presets made in Lightkey\'s own colour picker are never wrong.')
        for name, bgr, h_bgr, rgb, h_rgb, _v in suspects[:12]:
            renders = h_bgr if winner == 'bgr' else h_rgb
            print(f'     {str(name)[:34]:<35} named for {expected_for(name) or "?"}, '
                  f'renders {renders}')
        if len(suspects) > 12:
            print(f'     … and {len(suspects) - 12} more')
    return 0 if winner == 'bgr' else 1


if __name__ == '__main__':
    sys.exit(main())

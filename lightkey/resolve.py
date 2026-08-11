"""
Lightkey .lightkeyproj resolver

Reusable library for inspecting NSKeyedArchiver-encoded Lightkey project files.

Usage:
    from resolve import load, classname, resolve, find_instances

    data, objects = load('project.lightkeyproj')

    # List all cues
    for uid in find_instances(objects, 'LXCue'):
        cue = resolve(objects, uid, depth=2)
        print(cue.get('name'), cue.get('priority'))

Or for interactive exploration, use the module-level `data` and `objects`
after calling `load_into_module('project.lightkeyproj')`.
"""

import plistlib
from plistlib import UID
import uuid as _uuid

# Module-level state for the interactive-exploration pattern.
# Populated by load_into_module() below. Most callers should prefer load().
data = None
objects = None


def load(path):
    """Load a .lightkeyproj. Returns (data, objects)."""
    with open(path, 'rb') as f:
        d = plistlib.load(f)
    return d, d['$objects']


def load_into_module(path):
    """Populate module-level `data` and `objects` for interactive use."""
    global data, objects
    data, objects = load(path)
    return data, objects


def classname(objs, obj_or_uid):
    """Return the $classname of an object or the object at a UID.
    Returns None if the target has no class."""
    if isinstance(obj_or_uid, UID):
        obj = objs[int(obj_or_uid)]
    else:
        obj = obj_or_uid
    if not isinstance(obj, dict):
        return None
    cref = obj.get('$class')
    if not isinstance(cref, UID):
        return None
    cdef = objs[int(cref)]
    if isinstance(cdef, dict):
        return cdef.get('$classname')
    return None


def _decode_nsuuid(obj):
    b = obj.get('NS.uuidbytes')
    if isinstance(b, bytes) and len(b) == 16:
        return str(_uuid.UUID(bytes=b))
    return None


_COLL_CLASSES = {'NSArray', 'NSMutableArray', 'NSSet', 'NSMutableSet'}
_DICT_CLASSES = {'NSDictionary', 'NSMutableDictionary'}
_STRING_CLASSES = {'NSString', 'NSMutableString'}


def resolve(objs, ref, depth=6, seen=None):
    """Resolve a UID reference (or raw value) into a Python-native tree.
    Depth-limited to keep output manageable; cycles detected via seen set."""
    if seen is None:
        seen = set()

    if isinstance(ref, UID):
        idx = int(ref)
        if idx in seen:
            return f'<cycle-ref #{idx}>'
        if depth <= 0:
            return f'<ref #{idx} (deeper) class={classname(objs, objs[idx])}>'
        return resolve(objs, objs[idx], depth - 1, seen | {idx})

    if isinstance(ref, dict):
        cls = classname(objs, ref)

        if cls == 'NSUUID':
            return _decode_nsuuid(ref)

        if cls in _STRING_CLASSES:
            return ref.get('NS.string') or ref.get('NS.bytes')

        if cls in _COLL_CLASSES:
            items = ref.get('NS.objects', [])
            return [resolve(objs, x, depth - 1, seen) for x in items]

        if cls in _DICT_CLASSES:
            keys = ref.get('NS.keys', [])
            vals = ref.get('NS.objects', [])
            out = {}
            for k, v in zip(keys, vals):
                rk = resolve(objs, k, depth - 1, seen)
                rv = resolve(objs, v, depth - 1, seen)
                if not isinstance(rk, (str, int, float)):
                    rk = repr(rk)
                out[rk] = rv
            return out

        out = {'__class__': cls}
        for k, v in ref.items():
            if k == '$class':
                continue
            out[k] = resolve(objs, v, depth - 1, seen)
        return out

    if isinstance(ref, bytes):
        if len(ref) > 64:
            return f'<bytes len={len(ref)}>'
        return ref.hex()
    return ref


def find_instances(objs, class_name):
    """Return the UIDs of all objects whose $classname matches."""
    # Find the class-def UIDs for the target class name.
    cdef_uids = {
        i for i, o in enumerate(objs)
        if isinstance(o, dict) and o.get('$classname') == class_name
    }
    result = []
    for i, o in enumerate(objs):
        if isinstance(o, dict):
            cref = o.get('$class')
            if isinstance(cref, UID) and int(cref) in cdef_uids:
                result.append(i)
    return result


def class_inventory(objs):
    """Return {classname: instance_count} for every class in the archive."""
    from collections import Counter
    counts = Counter()
    for o in objs:
        cn = classname(objs, o) if isinstance(o, dict) else None
        if cn:
            counts[cn] += 1
    return dict(counts)


def top_keys(d):
    """Return the keys of $top, sorted."""
    return sorted(d['$top'].keys())


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('usage: python resolve.py <path-to-.lightkeyproj>')
        sys.exit(1)
    d, objs = load(sys.argv[1])
    print(f'Archive: {len(objs)} objects, {len(d["$top"])} top-level keys')
    print()
    print('Class inventory:')
    for name, n in sorted(class_inventory(objs).items()):
        print(f'  {name:<30} {n}')

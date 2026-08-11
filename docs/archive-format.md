# Archive format — NSKeyedArchiver binary plist

Every `.lightkeyproj` file is an **Apple binary plist** (`bplist00`) encoding an **NSKeyedArchiver** graph. Understanding this format is non-negotiable for safely modifying the file.

## File-level structure

The top-level plist has four keys:

```python
{
    '$version':  100000,        # archiver version (always this)
    '$archiver': 'NSKeyedArchiver',
    '$top':      {...},         # dict of named top-level roots
    '$objects':  [...],         # flat list of all objects, indexed by UID
}
```

You only ever modify `$top` and `$objects`. Never touch `$version` or `$archiver`.

## $objects — the flat graph

`$objects` is a Python `list` where every entry has an index position that serves as its UID. Objects reference each other by `UID` (a subclass of `int` exposed by Python's `plistlib`).

```python
from plistlib import UID
objects[42]                     # direct index
objects[int(some_uid_ref)]      # via UID reference
```

**Index 0 is always the string `'$null'`** — it represents nil/None. When a field optionally doesn't exist, it's set to `UID(0)`. Never put anything else at index 0.

### What kinds of objects live in $objects?

Three flavours:

1. **Class definitions** — dicts like `{'$classname': 'LXCue', '$classes': ['LXCue', 'LXCueObjC', 'NSObject']}`. Every instance of that class references this UID in its `$class` field. There's typically one class def per class in the entire archive.

2. **Instances** — dicts with a `$class` key pointing to the class definition. The rest of the dict is the instance's fields.

3. **Primitive values** — raw Python strings, ints, floats, bools, bytes, stored inline. Used for things like rect strings `'{{10, 20}, {100, 36}}'`, colour names `'Red'`, or the inner `fpStore` bytes of presets.

### Shared singletons

NSKeyedArchiver deduplicates content. In every Lightkey archive you will find:

- One **shared empty `NSArray`** at a low UID (e.g. 340) that is referenced from every `childNodes` field of every leaf preset. Don't create fresh empty arrays — reuse the singleton.
- One **shared empty `NSDictionary`** (e.g. UID 658 in the reference project) referenced as `metaModifiers`, `metaModifierDefaults`, `orphanPresetsGroup`'s empty slots. Same rule: reuse it.
- Sometimes a **shared `NSColor` white** (e.g. UID 212) used as fill/stroke for text items.

My `Builder.ns_array([])` and `Builder.ns_dict([])` helpers detect these on init and return the existing UID when asked for an empty collection.

## $top — named roots

`$top` is a dict mapping human-readable names to UIDs. Every reachable object in the file hangs off one of these roots. For a Lightkey project:

| Key | Points to | Notes |
|---|---|---|
| `universes` | `NSArray` of `LXDMXUniverse` | Fixture-to-address mapping |
| `fixtureProfiles` | `NSArray` of `LXFixtureProfile` | Fixture library |
| `rootPresetGroup` | `LXRootPresetGroup` | Top of the preset tree |
| `stages` | `NSArray` of `LXStage` | Visual stage layout(s) |
| `livePanels` | `NSArray` of `LXControlPanel` | All control panels in the project |
| `selectedLivePanel` | `LXControlPanel` | The currently-visible panel |
| `DMXBindingsCategory`, `MIDIBindingsCategory`, `keyBindingsCategory` | `LXBindingsCategory` | Input bindings |
| `movementPaths` | `NSArray` of `LXMovementPath` | Moving-head patterns |
| `fadeCurves` | `NSArray` | Usually empty |
| `adHocPreset`, `defaultsPreset` | `LXPreset` / `LXDefaultsPreset` | Runtime scratch / default state |
| `colorFavorites` | `NSArray` | User's saved colours |
| `appVersion`, `requiredAppVersion` | strings | e.g. `'5.9.1'` |
| `stageSnapshotData` | `NSDictionary` | Visual state snapshots |
| `effectTemplates` | `NSArray` | Lightkey's built-in effect library — usually empty in user files |
| `defaultCpanButton*`, `defaultCpanFrame*`, `defaultStageText*` | various | Defaults for new panel elements |
| `featureIdentifiersDisplayOrder`, `hiddenFeatureIdentifiers` | `NSArray` | UI preferences |
| `panAnglesIncludeInversion` | bool | Moving-head pan convention |
| `expandedNodeUUIDs` | `NSArray` | UI state of collapsed preset groups |

**Do not invent top-level keys.** If `$top` is missing a key that newer Lightkey versions expect, the file may fail to load on newer Lightkey builds — but add only keys you have seen in reference files.

## Reading the graph safely

The `lightkey/resolve.py` helper provides a safe resolver. Basic pattern:

```python
import plistlib
from plistlib import UID

with open('project.lightkeyproj', 'rb') as f:
    archive = plistlib.load(f)
objects = archive['$objects']

def deref(ref):
    """Follow a UID reference one step. Returns the target or None."""
    if ref is None or (isinstance(ref, UID) and int(ref) == 0):
        return None
    if isinstance(ref, UID):
        return objects[int(ref)]
    return ref  # already a value

def classname(obj):
    """Get the classname of an instance dict."""
    if not isinstance(obj, dict) or '$class' not in obj:
        return None
    cls_def = objects[int(obj['$class'])]
    return cls_def.get('$classname')

def find_instances(class_name):
    """Return UIDs of all instances of a given class."""
    result = []
    for i, obj in enumerate(objects):
        if isinstance(obj, dict) and '$class' in obj:
            cd = objects[int(obj['$class'])]
            if isinstance(cd, dict) and cd.get('$classname') == class_name:
                result.append(i)
    return result
```

## Writing the graph safely

Every `add(obj)` call must append to `$objects` and return the new UID. Never mutate an existing object's identity by editing it in place unless you are deliberately modifying in-place (e.g. changing `$top.livePanels` to point at a new array).

The critical rule: **UID references must stay valid after every add**. Because you're appending, they will — but if you ever delete or reorder `$objects`, everything breaks. Never do that.

## Schema versioning

Lightkey has evolved its schema at least once. Observed variants:

- **Older**: `fpStore` inner plist uses `umbrellaContainers` + `definedFeatures` + `segmentContainers`. This is what the reference project uses.
- **Newer**: `fpStore` inner plist uses `containers` + `subcontainers`. Observed in the Effects_Showcase.lightkeyproj file.

Newer versions may also add new fields to top-level classes. When in doubt, compare your generated objects' keys against a reference instance in the same file — not against a file of a different age.

See `fpstore-format.md` for details on both schemas.

## Binary plist vs. XML plist

Always write binary: `plistlib.dump(archive, f, fmt=plistlib.FMT_BINARY)`. Lightkey will probably accept XML too, but binary is the canonical format and avoids any whitespace/encoding edge cases.

Reading works the same either way (`plistlib.load(f)` detects format).

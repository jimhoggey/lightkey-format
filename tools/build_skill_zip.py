#!/usr/bin/env python3
"""
Build lightkey-patcher-skill.zip — the upload bundle for claude.ai's Skills UI.

claude.ai wants a different shape from a Claude Code plugin:

  * the ZIP must contain the skill FOLDER as its root, not loose files
  * SKILL.md must sit at the top of that folder (this repo keeps it in
    skills/lightkey-patcher/ so the plugin layout works)
  * frontmatter `description` is capped at 200 characters, and `name` at 64

So a plain "Download ZIP" from GitHub will not import. This script repackages the
same canonical sources into a bundle that does, and shortens the description to fit.

Usage:
    python3 tools/build_skill_zip.py                 # -> dist/lightkey-patcher-skill.zip
    python3 tools/build_skill_zip.py --out /tmp/x.zip
"""
import argparse
import os
import re
import shutil
import sys
import tempfile
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_NAME = 'lightkey-patcher'
SRC_SKILL = os.path.join(REPO, 'skills', SKILL_NAME, 'SKILL.md')

# claude.ai hard limits
MAX_NAME, MAX_DESC = 64, 200

# The canonical description is long and trigger-rich, which suits Claude Code.
# claude.ai caps it at 200 chars, so the bundle gets this one instead.
SHORT_DESC = ('Inspect and modify macOS Lightkey .lightkeyproj DMX lighting projects: '
              'format schemas, colour packing, panel building, and known failure modes.')

# Directories copied into the bundle, keeping their names so the paths written in
# SKILL.md (docs/..., lightkey/...) resolve unchanged.
PAYLOAD_DIRS = ['docs', 'lightkey', 'tools', 'examples']
PAYLOAD_FILES = ['LICENSE', 'README.md']

# Replaces the plugin-specific "where the files live" section.
LOCATION_SECTION = '''## Where the files referenced below live

Everything referenced here is bundled inside this skill folder — `docs/pitfalls.md`,
`lightkey/resolve.py` and so on are relative to the skill's own directory. Read them with
the Read tool as you need them; don't load all five docs at once.

The Python needs no dependencies beyond the standard library. From the skill directory:

```python
import sys; sys.path.insert(0, '.')          # or the absolute path to this skill folder
from lightkey.resolve import load, find_instances, classname
from lightkey.colour import pack_color, c8, unpack_rgb8
from lightkey.validate import Validator
```

Two CLI tools are bundled and should usually be your first move on a new file:

```bash
python3 tools/inspect_project.py  <project>.lightkeyproj   # structure, schema, groups
python3 tools/probe_colour.py     <project>.lightkeyproj   # prove the colour byte order
```

On claude.ai the user must upload their `.lightkeyproj` into the conversation before you
can read it, and anything you write must be offered back to them as a file download —
you cannot touch their local disk. Never hand back a modified project as the only copy;
tell them to keep their original.

'''


def build_skill_md():
    """Canonical SKILL.md -> bundle SKILL.md (short description, bundle-relative paths)."""
    text = open(SRC_SKILL, encoding='utf-8').read()
    if not text.startswith('---'):
        sys.exit('SKILL.md has no YAML frontmatter')
    end = text.index('---', 3)
    front, body = text[3:end], text[end + 3:]

    name = re.search(r'^name:\s*(.+)$', front, re.M).group(1).strip()
    if len(name) > MAX_NAME:
        sys.exit(f'name is {len(name)} chars, claude.ai allows {MAX_NAME}')
    if len(SHORT_DESC) > MAX_DESC:
        sys.exit(f'SHORT_DESC is {len(SHORT_DESC)} chars, claude.ai allows {MAX_DESC}')

    # Swap in the short description, dropping the long multi-line original.
    front = re.sub(r'^description:.*?(?=^\w+:|\Z)', f'description: {SHORT_DESC}\n',
                   front, flags=re.M | re.S)

    # Replace the plugin-relative location section with the bundle-relative one.
    body = re.sub(r'## Where the files referenced below live\n.*?(?=^## )',
                  LOCATION_SECTION, body, flags=re.M | re.S)

    # Fix references to the plugin/marketplace install, which don't apply here.
    body = body.replace('root of this\nplugin/repository', 'root of this skill folder')
    return f'---{front}---{body}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(REPO, 'dist',
                                                  f'{SKILL_NAME}-skill.zip'))
    args = ap.parse_args()

    skill_md = build_skill_md()
    desc = re.search(r'^description:\s*(.+)$', skill_md, re.M).group(1)
    print(f'description: {len(desc)}/{MAX_DESC} chars')

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, SKILL_NAME)
        os.makedirs(root)
        with open(os.path.join(root, 'SKILL.md'), 'w', encoding='utf-8') as f:
            f.write(skill_md)
        for d in PAYLOAD_DIRS:
            shutil.copytree(os.path.join(REPO, d), os.path.join(root, d),
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))
        for f in PAYLOAD_FILES:
            shutil.copy2(os.path.join(REPO, f), root)

        if os.path.exists(args.out):
            os.remove(args.out)
        count = 0
        with zipfile.ZipFile(args.out, 'w', zipfile.ZIP_DEFLATED) as z:
            for dirpath, _dirnames, filenames in os.walk(root):
                for fn in sorted(filenames):
                    full = os.path.join(dirpath, fn)
                    z.write(full, os.path.relpath(full, tmp))   # folder as ZIP root
                    count += 1

    size = os.path.getsize(args.out)
    print(f'wrote {args.out}  ({count} files, {size / 1024:.0f} KB)')
    print(f'ZIP root: {SKILL_NAME}/SKILL.md  <- required by claude.ai')


if __name__ == '__main__':
    main()

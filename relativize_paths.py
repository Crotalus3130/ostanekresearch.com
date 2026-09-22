#!/usr/bin/env python3
"""Make in-site links relative so the pages render when double-clicked off disk.

Why this exists
---------------
Every in-site reference was root-relative (`/assets/css/site.css`). A browser
resolves those against the ORIGIN. Served from ostanekresearch.com the origin is
the site root, so they work. Opened as a local file the origin is the FILESYSTEM
root, so the browser looks for `/assets/css/site.css` on the disk, finds nothing,
and renders unstyled HTML with no logo -- the white page Kevin hit. Nothing is
missing from the folder; only the path shape is wrong.

Two passes, deliberately separable (`--only`):

  assets  rewrite /assets/... -> depth-correct relative. Pure win, no URL change.
  links   rewrite page + directory links. Directory links additionally get an
          explicit `index.html`, because file:// does NOT serve index.html for a
          directory the way a web server does. Cost: deployed URLs read
          /field/index.html instead of /field/. Drop this pass to keep bare
          directory URLs, and accept that off-disk navigation stays broken.

`--check` proves the result off disk without a browser: it resolves every
relative reference against its own file's directory and asserts the target
exists. That covers all references, not one viewport.

Usage:
  python3 relativize_paths.py --check
  python3 relativize_paths.py --apply [--only assets|links]
"""

import argparse
import os
import re
import subprocess
import sys

# Only single-leading-slash values; `//host` (protocol-relative) is left alone.
REF = re.compile(r'(?P<attr>\bhref|\bsrc)="(?P<val>/(?!/)[^"]*)"')

ASSET_PREFIX = "/assets/"


def tracked_html(root):
    out = subprocess.run(
        ["git", "ls-files", "*.html"], cwd=root, capture_output=True, text=True
    )
    return sorted(p for p in out.stdout.split("\n") if p.strip())


def classify(val):
    return "assets" if val.startswith(ASSET_PREFIX) else "links"


def relativize(val, depth):
    """Root-relative value -> value relative to a file `depth` dirs below root."""
    target = val.lstrip("/")
    # file:// will not serve index.html for a bare directory; a web server will.
    if target == "" or target.endswith("/"):
        target += "index.html"
    return "../" * depth + target


def rewrite(root, only, apply_):
    files = tracked_html(root)
    changed, total = [], 0
    for rel in files:
        depth = len(rel.split(os.sep)) - 1
        path = os.path.join(root, rel)
        src = open(path, encoding="utf-8").read()
        n = [0]

        def sub(m):
            val = m.group("val")
            if only and classify(val) != only:
                return m.group(0)
            n[0] += 1
            return f'{m.group("attr")}="{relativize(val, depth)}"'

        out = REF.sub(sub, src)
        if n[0]:
            total += n[0]
            changed.append((rel, n[0]))
            if apply_:
                open(path, "w", encoding="utf-8").write(out)
    return changed, total


def check(root):
    """Assert every in-site reference resolves to a real file on disk."""
    files = tracked_html(root)
    absolute, missing, ok = [], [], 0
    for rel in files:
        base = os.path.dirname(os.path.join(root, rel))
        for m in re.finditer(r'(?:href|src)="([^"]+)"', open(os.path.join(root, rel), encoding="utf-8").read()):
            val = m.group(1)
            if val.startswith(("http://", "https://", "mailto:", "#", "//", "data:")):
                continue
            if val.startswith("/"):
                absolute.append((rel, val))
                continue
            target = os.path.normpath(os.path.join(base, val.split("#")[0]))
            if os.path.exists(target):
                ok += 1
            else:
                missing.append((rel, val))
    return absolute, missing, ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--only", choices=["assets", "links"])
    args = ap.parse_args()
    root = os.path.dirname(os.path.abspath(__file__))

    if args.check:
        absolute, missing, ok = check(root)
        print(f"resolve OK        : {ok}")
        print(f"still root-rel    : {len(absolute)}")
        for rel, val in absolute[:15]:
            print(f"    {rel}: {val}")
        print(f"dangling on disk  : {len(missing)}")
        for rel, val in missing[:15]:
            print(f"    {rel}: {val}")
        return 0 if not absolute and not missing else 1

    changed, total = rewrite(root, args.only, args.apply)
    verb = "rewrote" if args.apply else "would rewrite"
    print(f"{verb} {total} refs in {len(changed)} files"
          + (f" (pass: {args.only})" if args.only else ""))
    for rel, n in changed:
        print(f"    {n:4}  {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

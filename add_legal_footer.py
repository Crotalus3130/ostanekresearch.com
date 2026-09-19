#!/usr/bin/env python3
"""
add_legal_footer.py — put Terms / Refunds / Privacy / Contact in every footer.

Why: Paddle's domain-approval page states the bar — "Your website must link
through to, or contain, your: terms of service, privacy notice and refund
policy." Those pages exist at /orrery/{license,refunds,privacy}.html, but on
2026-09-19 nothing on the homepage linked to them. ostanekresearch.com was
submitted at the root, so a reviewer landing there saw no legal links at all.

Absolute hrefs, so the same line works from /, /field/ and /orrery/.
Idempotent: a file that already has the line is left alone. Drafts are skipped.
Run from anywhere; --check reports without writing.
"""

import argparse, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent
MARK = 'href="/orrery/license.html"'
LINE = ('    <p class="meta">'
        '<a href="/orrery/license.html">Terms</a> · '
        '<a href="/orrery/refunds.html">Refunds</a> · '
        '<a href="/orrery/privacy.html">Privacy</a> · '
        '<a href="mailto:kevin@ostanekresearch.com">Contact</a></p>\n')

# the last </div> before </footer>
CLOSE = re.compile(r"(\n[ \t]*</div>[ \t]*\n[ \t]*</footer>)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    changed, skipped, already, nofooter = [], [], [], []

    for path in sorted(ROOT.rglob("*.html")):
        rel = path.relative_to(ROOT)
        if "draft" in path.name.lower():
            skipped.append(rel)
            continue
        text = path.read_text(encoding="utf-8")
        if "<footer" not in text:
            nofooter.append(rel)
            continue
        if MARK in text:
            already.append(rel)
            continue
        new, n = CLOSE.subn(lambda m: "\n" + LINE.rstrip("\n") + m.group(1), text, count=1)
        if n != 1:
            nofooter.append(rel)      # footer shape did not match; leave it alone
            continue
        if not args.check:
            path.write_text(new, encoding="utf-8")
        changed.append(rel)

    verb = "would add" if args.check else "added"
    print(f"{verb} the legal footer to {len(changed)} files")
    for r in changed:
        print(f"  + {r}")
    for label, group in (("already had it", already), ("draft, skipped", skipped),
                         ("no matching footer", nofooter)):
        if group:
            print(f"\n{label}: {len(group)}")
            for r in group:
                print(f"    {r}")

    # Verify: re-read what we wrote and confirm all three links are present.
    if not args.check and changed:
        bad = [r for r in changed
               if not all(s in (ROOT / r).read_text(encoding="utf-8")
                          for s in ("/orrery/license.html", "/orrery/refunds.html",
                                    "/orrery/privacy.html"))]
        if bad:
            print("\nVERIFY FAILED:", *bad, sep="\n  ")
            sys.exit(1)
        print("\nverified — all three links present in every file written")


if __name__ == "__main__":
    main()

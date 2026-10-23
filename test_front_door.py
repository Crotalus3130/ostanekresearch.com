#!/usr/bin/env python3
"""test_front_door.py — checks the front door against the built site.

Run from the site root:  python3 test_front_door.py

These are assertions about the repo as it stands, not unit tests against
fixtures. That is deliberate: the failure this guards against is not a logic
bug in isolation, it is the site drifting out from under the generator —
a hand-edited head, a new page nobody ran the tool over, a feed that stopped
matching the index. Checking the real files is the only way to catch that.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET

SITE = pathlib.Path(__file__).resolve().parent
SM = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
ORIGIN = "https://ostanekresearch.com"

failures: list[str] = []
checks = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if ok:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))
        failures.append(label)


def tracked(pattern: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", pattern], cwd=SITE, capture_output=True, text=True
    ).stdout
    return sorted(p for p in out.split("\n") if p)


def main() -> int:
    pages = tracked("*.html")
    texts = {p: (SITE / p).read_text(encoding="utf-8") for p in pages}

    print(f"front door — {len(pages)} published pages\n")

    print("every published page carries the block")
    for p in pages:
        check(p, "front_door:begin" in texts[p] and "front_door:end" in texts[p])

    print("\nexactly one of each tag per page (no duplicates from a re-run)")
    for tag in ("og:title", "og:description", "og:image", "og:url",
                "og:site_name", "twitter:card", 'rel="canonical"', "feed.xml"):
        counts = {p: texts[p].count(tag) for p in pages}
        off = {p: n for p, n in counts.items() if n != 1}
        check(tag, not off, str(off))

    print("\nhand-written values survived")
    check(
        "index.html kept its own og:description",
        "A Mac app that keeps an AI's identity on your computer. $79, bought once."
        in texts["index.html"],
    )
    check(
        "book/index.html kept its own og:title",
        'content="A Natural History of Man: Field Observations by Living Machines"' in texts["book/index.html"],
    )

    print("\nthe post-purchase page is not offered to search engines")
    check("thanks.html noindex", 'content="noindex, follow"' in texts["orrery/thanks.html"])
    check(
        "no other page is noindex",
        sum("noindex" in t for t in texts.values()) == 1,
    )

    print("\nthe essays that were shared carry their own picture, not the logo")
    for page, img in (
        ("field/moral-weight.html", "assets/orrery/bedtime-2026-06-01.png"),
        ("field/orrery-is-out.html", "assets/orrery/ditch-check-2026-06-05.png"),
        ("field/the-beagle-principle.html", "assets/mark/gemini-manifold.jpg"),
    ):
        check(page, f'og:image" content="{ORIGIN}/{img}"' in texts[page])

    print("\nevery og:image and og:url points at something real")
    assets = set(tracked("assets")) | set(tracked("book"))
    import re

    for p in pages:
        for m in re.finditer(r'(og:image|twitter:image)" content="([^"]+)"', texts[p]):
            rel = m.group(2).removeprefix(ORIGIN + "/")
            check(f"{p} → {rel}", rel in assets, "not a tracked asset")

    print("\nevery og:url and canonical points at its own page, index folded")
    def canon(p: str) -> str:
        if p == "index.html":
            return f"{ORIGIN}/"
        if p.endswith("/index.html"):
            return f"{ORIGIN}/{p[: -len('index.html')]}"
        return f"{ORIGIN}/{p}"

    for p in pages:
        check(f"{p} → {canon(p)}",
              f'og:url" content="{canon(p)}"' in texts[p]
              and f'rel="canonical" href="{canon(p)}"' in texts[p])

    print("\nsitemap")
    sm = ET.parse(SITE / "sitemap.xml").getroot()
    locs = [e.text for e in sm.iter(f"{SM}loc")]
    check("parses and is a urlset", sm.tag == f"{SM}urlset")
    check("no duplicate urls", len(locs) == len(set(locs)))
    allowed = {canon(p) for p in pages}
    check(
        "every url is a published page",
        all(u in allowed for u in locs),
        str([u for u in locs if u not in allowed]),
    )
    check("thanks.html is absent", f"{ORIGIN}/orrery/thanks.html" not in locs)
    for draft in ("index.store.draft.html", "indexdraft.html",
                  "index copy.html"):
        check(f"no untracked draft leaked: {draft}", f"{ORIGIN}/{draft}" not in locs)
    check("every lastmod is a date", all(
        len(e.text) == 10 and e.text[4] == "-" for e in sm.iter(f"{SM}lastmod")))

    print("\nrobots.txt")
    robots = (SITE / "robots.txt").read_text(encoding="utf-8")
    check("points at the sitemap", f"Sitemap: {ORIGIN}/sitemap.xml" in robots)
    check("allows everything", "Allow: /" in robots and "Disallow:" not in robots)

    print("\nfeed")
    feed = ET.parse(SITE / "feed.xml").getroot()
    items = feed.findall(".//item")
    check("parses as rss", feed.tag == "rss")
    index_html = texts["field/index.html"]
    cards = index_html.count('<div class="card">')
    check("one item per card on the field index", len(items) == cards,
          f"{len(items)} items vs {cards} cards")
    check("items are newest-first", [i.findtext("pubDate") for i in items] ==
          sorted((i.findtext("pubDate") for i in items),
                 key=lambda s: __import__("email.utils", fromlist=["x"])
                 .parsedate_to_datetime(s), reverse=True))
    check("every item links to a published page",
          all(i.findtext("link").removeprefix(ORIGIN + "/") in pages for i in items))
    check("every item has an author",
          all((i.findtext("{http://purl.org/dc/elements/1.1/}creator") or "").strip()
              for i in items))
    check("every item has a guid", all(i.findtext("guid") for i in items))

    print("\nJSON-LD structured data")
    import json as _json_test
    ORRERY_APP = {"orrery/index.html", "orrery/download.html"}
    field_notes = [p for p in pages
                   if p.startswith("field/") and p != "field/index.html"]
    for p in field_notes + list(ORRERY_APP) + ["index.html"]:
        check(f"{p} has JSON-LD", "application/ld+json" in texts[p])
    # Pages that should NOT get JSON-LD
    for p in ["book/index.html", "field/index.html", "orrery/thanks.html",
              "orrery/license.html", "orrery/privacy.html", "orrery/refunds.html",
              "orrery/psi-format.html", "orrery/soul-return.html"]:
        if p in texts:
            check(f"{p} has no JSON-LD", "application/ld+json" not in texts[p])
    # JSON-LD blocks parse as valid JSON with the right @type
    import re as _re_test
    JSONLD_RE = re.compile(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>', re.S
    )
    for p in field_notes:
        m = JSONLD_RE.search(texts[p])
        if m:
            try:
                d = _json_test.loads(m.group(1))
                check(f"{p} JSON-LD @type=Article", d.get("@type") == "Article")
                if d.get("author"):
                    check(f"{p} JSON-LD author present",
                          bool(d["author"].get("name")))
            except Exception as exc:
                check(f"{p} JSON-LD parses", False, str(exc))
        else:
            check(f"{p} JSON-LD parseable (no block found)", False)
    for p in ORRERY_APP:
        m = JSONLD_RE.search(texts[p])
        if m:
            try:
                d = _json_test.loads(m.group(1))
                check(f"{p} JSON-LD @type=SoftwareApplication",
                      d.get("@type") == "SoftwareApplication")
                check(f"{p} JSON-LD price present",
                      d.get("offers", {}).get("price") == "79.00")
            except Exception as exc:
                check(f"{p} JSON-LD parses", False, str(exc))
    m = JSONLD_RE.search(texts["index.html"])
    if m:
        try:
            d = _json_test.loads(m.group(1))
            check("index.html JSON-LD @type=WebSite", d.get("@type") == "WebSite")
        except Exception as exc:
            check("index.html JSON-LD parses", False, str(exc))
    # No page has more than one JSON-LD block
    for p in pages:
        n = texts[p].count("application/ld+json")
        check(f"{p} at most one JSON-LD block", n <= 1, f"found {n}")

    print("\nthe generator is idempotent")
    again = subprocess.run(
        [sys.executable, "front_door.py", "--check"],
        cwd=SITE, capture_output=True, text=True,
    )
    check("a second --check finds nothing to do", again.returncode == 0,
          again.stdout.strip().split("\n")[-1] if again.stdout else "")

    print(f"\n{checks - len(failures)}/{checks} green")
    if failures:
        print("FAILED:")
        for f in failures:
            print(f"  · {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

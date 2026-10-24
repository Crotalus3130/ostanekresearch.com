#!/usr/bin/env python3
"""front_door.py — make every published page shareable and findable.

Measured 2026-10-15, before this existed: of 28 published pages, 2 had an
Open Graph card. `field/moral-weight.html` — the essay posted to two Reddit
communities on 10-14 and emailed to seven writers on 10-13 — had none. Every
one of those shares rendered as a bare URL: no headline, no picture, no
summary. There was also no sitemap.xml, no robots.txt, no feed, and no
canonical tag anywhere on the site, so search engines crawled slowly and a
reader who liked a piece had no way to be told about the next one.

None of that is a writing problem. It is a plumbing problem, and plumbing is
the kind of thing a script should hold rather than a person.

WHAT IT DOES

  1. For every published page, writes the social/search block into <head>:
     og:title, og:description, og:image, og:url, twitter:card, rel=canonical,
     and the feed link.
  2. Writes sitemap.xml over the published, reachable page set.
  3. Writes robots.txt pointing at the sitemap.
  4. Writes feed.xml (RSS 2.0) from the field-notes index.
  5. Writes a "Read next" block into the body of every field note.
  6. Reports what changed and what is still missing.

THE READ-NEXT BLOCK, and why it exists (added 2026-10-24)

  Measured before writing it: all 22 published field notes carried the same
  link set — four nav links and four footer links, byte-identical boilerplate.
  Note-to-note links: zero. So a reader who arrived at one note from a search
  result or from Kevin's Reddit comment had exactly one onward move, the back
  button, and a crawler saw 22 leaves hanging off one index with no topical
  graph between them. The index lists every note; nothing listed a second note
  to anyone standing on the first.

  Each note now ends with three cards. The first is always the next-older note
  in date order, wrapping from the oldest back to the newest. That edge is a
  single cycle through all 22, which is what makes the guarantee cheap to state
  and cheap to test: every note is pointed at by at least one other note, no
  matter how the similarity scoring behaves. The remaining two are the notes
  with the highest IDF-weighted token overlap on title + summary, so the slots
  that carry relevance cannot cost the slot that carries connectivity.

  The card text — pill, title, byline, date, summary — is lifted verbatim from
  the hand-written cards on field/index.html, the same source feed.xml already
  republishes. DERIVE, NEVER INVENT holds, with one bounded exception stated
  plainly rather than hidden: the heading "Read next" is two words this tool
  writes. The trailing link reads "Field notes", which is the site's own nav
  wording.

  One hazard worth naming, because it is the kind this house keeps re-learning:
  these generated links must NOT count as the site linking to a page. If they
  did, a note nobody linked by hand would be promoted into the sitemap on the
  strength of a link this tool wrote about itself. `Page.clean` strips the
  read-next block for exactly that reason, so `reachable()` only ever sees
  human-written navigation.

DESIGN CONSTRAINTS, and why:

  * DERIVE, NEVER INVENT. Every page already has a hand-written <title> and
    <meta name="description">, specific and good. This tool copies those into
    the fields the platforms actually read. It writes no prose of its own, so
    no sentence reaches a stranger that a person in this house did not write.
    That also keeps it clear of the dignity filter — it has nothing to decide.

  * FILL GAPS, NEVER OVERWRITE. index.html and book/index.html have
    hand-written og tags. The tool emits only tags a page is missing, so those
    values survive untouched and no page ends up with duplicates. Where a
    hand-written og:title has drifted from the page's own <title>, that is
    reported for a human, not silently reconciled.

  * PUBLISHED = GIT-TRACKED, not on-disk. Pages is served from the commit, so
    the working tree over-reports: 9 drafts, previews and .bak files sit beside
    the real pages. A sitemap built from a glob would hand a search engine URLs
    the site never published. The page set is `git ls-files '*.html'`.

  * THE SITEMAP NEVER PROMOTES WHAT THE SITE DOES NOT LINK. A page that is
    published but unreachable from the site's own navigation is listed in the
    report and left out of the sitemap. Submitting it would be a publishing
    decision, and that is Kevin's.

  * IDEMPOTENT. Everything written lives between front_door markers and is
    replaced whole on each run. Hand edits outside the markers survive. Run it
    twice and the second run reports zero changes; that property is what makes
    it safe on a timer.

  * ZERO NETWORK. It reads the repo and writes the repo. It never fetches, never
    posts, never pings a service. It cannot send anything anywhere.

USAGE

  python3 front_door.py --check     # report only, changes nothing, exit 1 if work is pending
  python3 front_door.py --write     # do it
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import html as _html
import json as _json
import math
import pathlib
import posixpath
import re
import subprocess
import sys
from email.utils import format_datetime
from xml.sax.saxutils import escape as xml_escape

SITE = pathlib.Path(__file__).resolve().parent
ORIGIN = "https://ostanekresearch.com"

BEGIN = "<!-- front_door:begin — generated by front_door.py; edit the title/description above, not here -->"
END = "<!-- front_door:end -->"

# The body block. A second marker pair, because the head block is replaced
# whole on every run and these two live in different parts of the document.
RN_BEGIN = (
    "<!-- front_door:readnext:begin — generated by front_door.py from the cards "
    "on field/index.html; edit those cards, not this -->"
)
RN_END = "<!-- front_door:readnext:end -->"

# Three: one connectivity edge plus two relevance slots. Changing this changes
# how many relevance slots there are; the connectivity edge is always first.
READ_NEXT_COUNT = 3

DEFAULT_IMAGE = "assets/mark/ostanek-research-night.jpg"

# Orrery product pages — receive SoftwareApplication JSON-LD.
ORRERY_APP_PAGES = {"orrery/index.html", "orrery/download.html"}

# Canonical once-off price. price_audit.py is the gate that keeps this honest;
# update both together if the price changes.
ORRERY_ONCE_PRICE = "79.00"

# Pages that are published but must never be handed to a search engine.
# thanks.html is what a buyer sees after paying; it is not a front door.
NOINDEX = {"orrery/thanks.html"}

# The page the crawl starts from when working out what the site links to.
ROOTS = ["index.html"]

# Analytics counter URL (GoatCounter). Set once to add cookie-free page-view
# counting to every page. Steps: (1) create a free account at goatcounter.com,
# (2) set this to your count URL, (3) run `python3 front_door.py --write`,
# (4) commit and push. Leave empty to disable. No account = no data collected.
# Example: GOATCOUNTER_URL = "https://ostanekresearch.goatcounter.com/count"
GOATCOUNTER_URL = ""


# ---------------------------------------------------------------- git helpers

def git(*args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=SITE, capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def published_pages() -> list[str]:
    """The pages Pages actually serves: tracked HTML, nothing else."""
    return sorted(p for p in git("ls-files", "*.html").split("\n") if p)


def published_assets() -> set[str]:
    return {p for p in git("ls-files", "assets").split("\n") if p}


def last_modified(relpath: str) -> str:
    """Commit date of the page's last change, as a sitemap lastmod date."""
    out = git("log", "-1", "--format=%cI", "--", relpath).strip()
    return out[:10] if out else dt.date.today().isoformat()


# ------------------------------------------------------------------- the page

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)
DESC_RE = re.compile(
    r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']\s*/?>', re.I | re.S
)
IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)
HEAD_END_RE = re.compile(r"</head>", re.I)
BLOCK_RE = re.compile(
    re.escape(BEGIN) + r".*?" + re.escape(END), re.S
)
# Marker-independent: matches the block even if BEGIN's comment text was edited.
LOOSE_BLOCK_RE = re.compile(
    r"<!--\s*front_door:begin.*?<!--\s*front_door:end\s*-->", re.S
)
RN_BLOCK_RE = re.compile(
    r"<!--\s*front_door:readnext:begin.*?<!--\s*front_door:readnext:end\s*-->", re.S
)
# Where the read-next block goes. Measured 2026-10-24: 21 of 22 notes close an
# <article>; field/the-missing-report-channel.html is hand-built and has none,
# so an </article>-only anchor would have skipped it in silence. Every note has
# a <footer>, which is the fallback. Neither present → refuse, never guess.
ARTICLE_END_RE = re.compile(r"</article\s*>", re.I)
FOOTER_START_RE = re.compile(r"<footer\b", re.I)


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def url_for(relpath: str) -> str:
    """The one canonical URL for a page.

    An index folds into its directory: `field/index.html` canonicalises to
    `/field/`. Both forms are served and the site's own navigation links the
    .html form, so without this a page's ranking signal splits across two URLs
    that are the same page. Consolidating them is the entire job of a canonical
    tag, so it is worth not getting lazy about."""
    if relpath == "index.html":
        return f"{ORIGIN}/"
    if relpath.endswith("/index.html"):
        return f"{ORIGIN}/{relpath[: -len('index.html')]}"
    return f"{ORIGIN}/{relpath}"


def resolve(relpath: str, href: str) -> str:
    """Resolve a page-relative href to a repo-relative path."""
    base = pathlib.PurePosixPath(relpath).parent
    try:
        return str((base / href).as_posix()).replace("/./", "/") if href else ""
    except ValueError:
        return ""


def normalise(p: str) -> str:
    parts: list[str] = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts)


class Page:
    def __init__(self, relpath: str, assets: set[str]):
        self.rel = relpath
        self.path = SITE / relpath
        self.raw = self.path.read_text(encoding="utf-8")
        # The page without any generated block, so existing-tag detection does
        # not see this tool's own previous output as hand-written — and so
        # links() reports only navigation a person wrote. The read-next block
        # must be stripped here or the tool would certify its own output:
        # a note linked by nobody would become "reachable" because we linked
        # it, and land in the sitemap on that basis.
        self.clean = RN_BLOCK_RE.sub("", LOOSE_BLOCK_RE.sub("", self.raw))

        m = TITLE_RE.search(self.clean)
        self.title = strip_tags(m.group(1)) if m else ""
        m = DESC_RE.search(self.clean)
        self.description = strip_tags(m.group(1)) if m else ""
        self.image = self._pick_image(assets)
        self.noindex = relpath in NOINDEX
        # Populated by main() for field notes, using data from the field index cards.
        self.field_meta: dict | None = None
        # Populated by main(): the index-card dicts for this note's read-next cards.
        self.read_next: list[dict] = []

    def _pick_image(self, assets: set[str]) -> str:
        """The page's own first published image, else the house mark. A shared
        essay should show its own evidence, not a logo."""
        for href in IMG_RE.findall(self.clean):
            if "://" in href or href.startswith("data:"):
                continue
            cand = normalise(resolve(self.rel, href))
            if cand in assets:
                return cand
        return DEFAULT_IMAGE

    def has(self, needle: str) -> bool:
        return needle.lower() in self.clean.lower()

    def existing_og_title(self) -> str | None:
        m = re.search(
            r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']',
            self.clean, re.I | re.S,
        )
        return strip_tags(m.group(1)) if m else None

    # --------------------------------------------------------- structured data

    def jsonld(self) -> str:
        """JSON-LD structured data, derived from what this page already declares.

        Values come only from <title> and <meta name="description"> (both
        hand-written) plus field_meta populated from the index cards. Nothing
        is invented — same principle as the rest of this tool."""
        if not self.description:
            return ""
        url = url_for(self.rel)
        data: dict | None = None

        if self.rel == "index.html":
            data = {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": "Ostanek Research",
                "url": ORIGIN + "/",
                "description": self.description,
            }
        elif self.rel in ORRERY_APP_PAGES:
            data = {
                "@context": "https://schema.org",
                "@type": "SoftwareApplication",
                "name": "Orrery",
                "description": self.description,
                "url": url,
                "operatingSystem": "macOS",
                "applicationCategory": "UtilitiesApplication",
                "offers": {
                    "@type": "Offer",
                    "price": ORRERY_ONCE_PRICE,
                    "priceCurrency": "USD",
                },
            }
        elif self.rel.startswith("field/") and self.rel != "field/index.html":
            data = {
                "@context": "https://schema.org",
                "@type": "Article",
                "headline": self.title,
                "description": self.description,
                "url": url,
                "publisher": {
                    "@type": "Organization",
                    "name": "Ostanek Research",
                    "url": ORIGIN,
                },
            }
            if self.field_meta:
                data["author"] = {
                    "@type": "Person",
                    "name": self.field_meta["author"],
                }
                data["datePublished"] = self.field_meta["date"]

        if data is None:
            return ""
        body = _json.dumps(data, indent=2, ensure_ascii=False)
        return f'<script type="application/ld+json">\n{body}\n</script>'

    # -------------------------------------------------------------- the block

    def block(self) -> str:
        lines = [BEGIN]
        add = lines.append

        if not self.has("rel=\"canonical\"") and not self.has("rel='canonical'"):
            add(f'<link rel="canonical" href="{esc(url_for(self.rel))}">')

        if not self.has("og:title") and self.title:
            add(f'<meta property="og:title" content="{esc(self.title)}">')
        if not self.has("og:description") and self.description:
            add(f'<meta property="og:description" content="{esc(self.description)}">')
        if not self.has("og:image"):
            add(f'<meta property="og:image" content="{esc(ORIGIN)}/{esc(self.image)}">')
        if not self.has("og:url"):
            add(f'<meta property="og:url" content="{esc(url_for(self.rel))}">')
        if not self.has("og:type"):
            kind = "article" if self.rel.startswith("field/") and not self.rel.endswith("field/index.html") else "website"
            add(f'<meta property="og:type" content="{kind}">')
        if not self.has("og:site_name"):
            add('<meta property="og:site_name" content="Ostanek Research">')
        if not self.has("twitter:card"):
            add('<meta name="twitter:card" content="summary_large_image">')
        if not self.has("twitter:image"):
            add(f'<meta name="twitter:image" content="{esc(ORIGIN)}/{esc(self.image)}">')

        add(
            '<link rel="alternate" type="application/rss+xml" '
            f'title="Ostanek Research — field notes" href="{esc(ORIGIN)}/feed.xml">'
        )
        if self.noindex:
            add('<meta name="robots" content="noindex, follow">')

        ld = self.jsonld()
        if ld and not self.has("application/ld+json"):
            add(ld)

        if GOATCOUNTER_URL and not self.has("gc.zgo.at/count.js"):
            add(
                f'<script data-goatcounter="{esc(GOATCOUNTER_URL)}" '
                f'async src="//gc.zgo.at/count.js"></script>'
            )

        add(END)
        return "\n".join(lines)

    # ----------------------------------------------------------- read next

    def read_next_block(self) -> str:
        """Three cards, text lifted verbatim from the field index cards."""
        if not self.read_next:
            return ""

        def t(s: str) -> str:
            # The card text has already been through strip_tags, so any entity
            # in it is literal source text. Unescape before escaping or a
            # second run would turn &amp; into &amp;amp;.
            return esc(_html.unescape(s))

        lines = [
            RN_BEGIN,
            '<section class="section read-next" aria-label="Read next">',
            "<h2>Read next</h2>",
            '<div class="card-grid">',
        ]
        for card in self.read_next:
            lines += [
                '<div class="card">',
                f'<p class="voice-pill">{t(card["pill"])}</p>',
                f'<h3><a href="{esc(href_from(self.rel, card["rel"]))}">'
                f'{t(card["title"])}</a></h3>',
                f'<p class="meta">{t(card["author"])} · {t(card["date"])}</p>',
                f'<p>{t(card["summary"])}</p>',
                "</div>",
            ]
        lines += [
            "</div>",
            f'<p class="meta"><a href="'
            f'{esc(href_from(self.rel, "field/index.html"))}">Field notes</a></p>',
            "</section>",
            RN_END,
        ]
        return "\n".join(lines)

    def with_read_next(self, text: str) -> str:
        block = self.read_next_block()
        if not block:
            # No cards for this page: remove a stale block if one is there,
            # rather than leaving output from a run with different inputs.
            return RN_BLOCK_RE.sub("", text)
        if RN_BLOCK_RE.search(text):
            return RN_BLOCK_RE.sub(lambda _: block, text, count=1)
        m = ARTICLE_END_RE.search(text)
        if m:
            return text[: m.end()] + "\n" + block + text[m.end():]
        m = FOOTER_START_RE.search(text)
        if m:
            # At the start of the footer's line, so the footer keeps its indent.
            ls = text.rfind("\n", 0, m.start()) + 1
            return text[:ls] + block + "\n" + text[ls:]
        raise SystemExit(
            f"{self.rel}: no </article> and no <footer>, refusing to guess "
            "where the read-next block goes"
        )

    def rendered(self) -> str:
        block = self.block()
        if LOOSE_BLOCK_RE.search(self.raw):
            out = LOOSE_BLOCK_RE.sub(lambda _: block, self.raw, count=1)
        else:
            m = HEAD_END_RE.search(self.raw)
            if not m:
                raise SystemExit(f"{self.rel}: no </head>, refusing to guess")
            out = self.raw[: m.start()] + block + "\n" + self.raw[m.start():]
        return self.with_read_next(out)

    def links(self) -> set[str]:
        out = set()
        for href in re.findall(r'<a[^>]+href=["\']([^"\']+)["\']', self.clean, re.I):
            if "://" in href or href.startswith(("mailto:", "#", "data:")):
                continue
            out.add(normalise(resolve(self.rel, href.split("#")[0].split("?")[0])))
        return out


def esc(s: str) -> str:
    return (
        s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
    )


def href_from(src: str, dst: str) -> str:
    """A page-relative href from one repo path to another."""
    base = posixpath.dirname(src)
    return posixpath.relpath(dst, base) if base else dst


# ------------------------------------------------------------- read next plan

# Deliberately small: common English joiners that would otherwise dominate the
# overlap between two notes written by the same five people about one subject.
RN_STOPWORDS = frozenset(
    """
    about after again against because been before being between both cannot
    could does doing done down during each from have having here into itself
    just like made make many more most much must never only other over same
    should since some such than that them then there these they thing things
    this those through time under until very were what when where which while
    will with within without would your
    """.split()
)

RN_WORD_RE = re.compile(r"[a-z]{4,}")


def rn_tokens(text: str) -> set[str]:
    return {w for w in RN_WORD_RE.findall(_html.unescape(text).lower())
            if w not in RN_STOPWORDS}


def read_next_plan(items: list[dict], count: int = READ_NEXT_COUNT) -> dict[str, list[dict]]:
    """For each field note, the cards that follow it.

    Slot 1 is the next-older note, wrapping from the oldest to the newest.
    Those edges form one cycle through every note, so each note is pointed at
    by at least one other whatever the scoring does — connectivity never
    competes with relevance for a slot.

    Slots 2..count are the notes sharing the most IDF-weighted vocabulary on
    title + summary. Ties fall back to newest-first, which is the order the
    list already carries, so the result is deterministic.
    """
    # date descending, path ascending inside a date — fixed, so two runs on the
    # same input cannot disagree.
    order = sorted(sorted(items, key=lambda i: i["rel"]),
                   key=lambda i: i["date"], reverse=True)
    n = len(order)
    if n < 2:
        return {}

    docs = {it["rel"]: rn_tokens(f"{it['title']} {it['summary']}") for it in order}
    df: collections.Counter = collections.Counter()
    for toks in docs.values():
        df.update(toks)
    idf = {tok: math.log(n / c) + 1.0 for tok, c in df.items()}

    plan: dict[str, list[dict]] = {}
    for i, it in enumerate(order):
        rel = it["rel"]
        chosen = [order[(i + 1) % n]]
        taken = {rel, chosen[0]["rel"]}
        scored = [
            (sum(idf[t] for t in docs[rel] & docs[o["rel"]]), o)
            for o in order
            if o["rel"] not in taken
        ]
        # Stable: equal scores keep `order`'s newest-first sequence.
        scored.sort(key=lambda s: -s[0])
        for _score, other in scored:
            if len(chosen) >= count:
                break
            chosen.append(other)
        plan[rel] = chosen
    return plan


# ------------------------------------------------------------- reachable set

def reachable(pages: dict[str, Page]) -> set[str]:
    """Pages the site links to, from the front page outward. A published page
    nobody links to is reported, not promoted."""
    seen: set[str] = set()
    queue = [r for r in ROOTS if r in pages]
    while queue:
        cur = queue.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for link in pages[cur].links():
            if link in pages and link not in seen:
                queue.append(link)
    return seen


# ----------------------------------------------------------------- the feed

CARD_RE = re.compile(
    r'<div class="card">\s*'
    r'<p class="voice-pill">(?P<pill>.*?)</p>\s*'
    r'<h3><a href="(?P<href>[^"]+)">(?P<title>.*?)</a></h3>\s*'
    r'<p class="meta">(?P<meta>.*?)</p>\s*'
    r"<p>(?P<summary>.*?)</p>",
    re.S,
)
META_RE = re.compile(r"^(?P<author>.*?)\s*·\s*(?P<date>\d{4}-\d{2}-\d{2})")


def feed_items(pages: dict[str, Page]) -> list[dict]:
    index = pages.get("field/index.html")
    if index is None:
        return []
    items = []
    for m in CARD_RE.finditer(index.clean):
        rel = normalise(resolve("field/index.html", m.group("href")))
        if rel not in pages:
            continue
        meta = META_RE.match(strip_tags(m.group("meta")))
        if not meta:
            continue
        items.append(
            {
                "rel": rel,
                "pill": strip_tags(m.group("pill")),
                "title": strip_tags(m.group("title")),
                "author": meta.group("author").strip(),
                "date": meta.group("date"),
                "summary": strip_tags(m.group("summary")),
            }
        )
    items.sort(key=lambda i: i["date"], reverse=True)
    return items


def build_feed(items: list[dict]) -> str:
    def pub(datestr: str) -> str:
        d = dt.datetime.strptime(datestr, "%Y-%m-%d").replace(
            hour=12, tzinfo=dt.timezone.utc
        )
        return format_datetime(d)

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">',
        "<channel>",
        "<title>Ostanek Research — field notes</title>",
        f"<link>{url_for('field/index.html')}</link>",
        "<description>Writing from the practice — Kevin Ostanek, Ara Kovač, "
        "Claude Vardjan, Ara Novak, Gemini.</description>",
        "<language>en</language>",
        f'<atom:link href="{ORIGIN}/feed.xml" rel="self" type="application/rss+xml"/>',
    ]
    if items:
        out.append(f"<lastBuildDate>{pub(items[0]['date'])}</lastBuildDate>")
    for it in items:
        link = url_for(it["rel"])
        out += [
            "<item>",
            f"<title>{xml_escape(it['title'])}</title>",
            f"<link>{xml_escape(link)}</link>",
            f'<guid isPermaLink="true">{xml_escape(link)}</guid>',
            f"<dc:creator>{xml_escape(it['author'])}</dc:creator>",
            f"<pubDate>{pub(it['date'])}</pubDate>",
            f"<description>{xml_escape(it['summary'])}</description>",
            "</item>",
        ]
    out += ["</channel>", "</rss>", ""]
    return "\n".join(out)


def build_sitemap(pages: dict[str, Page], listed: list[str]) -> str:
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for rel in listed:
        out += [
            "<url>",
            f"<loc>{xml_escape(url_for(rel))}</loc>",
            f"<lastmod>{last_modified(rel)}</lastmod>",
            "</url>",
        ]
    out += ["</urlset>", ""]
    return "\n".join(out)


def build_robots() -> str:
    return (
        "# ostanekresearch.com\n"
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {ORIGIN}/sitemap.xml\n"
    )


# ---------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="report only, write nothing")
    g.add_argument("--write", action="store_true", help="apply")
    args = ap.parse_args()

    assets = published_assets()
    rels = published_pages()
    pages = {r: Page(r, assets) for r in rels}

    # Enrich field notes with author/date from the index cards, so JSON-LD
    # Article schema can include them. This must come before the change-diff.
    items = feed_items(pages)
    for item in items:
        if item["rel"] in pages:
            pages[item["rel"]].field_meta = item

    # Read-next cards, likewise before the change-diff. The plan is computed
    # over the index cards only, so a page that is not listed as a field note
    # gets no block — including field/index.html, which already lists them all.
    plan = read_next_plan(items)
    for rel, cards in plan.items():
        if rel in pages:
            pages[rel].read_next = cards

    linked = reachable(pages)
    orphans = [r for r in rels if r not in linked and r not in NOINDEX]
    listed = [r for r in rels if r in linked and r not in NOINDEX]

    # What would change.
    page_changes = [r for r, p in pages.items() if p.rendered() != p.raw]
    artefacts = {
        "sitemap.xml": build_sitemap(pages, listed),
        "robots.txt": build_robots(),
        "feed.xml": build_feed(feed_items(pages)),
    }
    artefact_changes = [
        name
        for name, body in artefacts.items()
        if not (SITE / name).exists()
        or (SITE / name).read_text(encoding="utf-8") != body
    ]

    # Report.
    print(f"front_door — {len(rels)} published pages (git-tracked)\n")
    print(f"{'page':44}{'card':>7}{'canon':>7}{'feed':>7}{'image':>34}")
    canonical_needle = 'rel="canonical"'
    for rel in rels:
        p = pages[rel]
        card = "yes" if p.has("og:title") else "ADD"
        canon = "yes" if p.has(canonical_needle) else "ADD"
        feed = "yes" if p.has("feed.xml") else "ADD"
        img = p.image.replace("assets/", "")
        print(f"{rel:44}{card:>7}{canon:>7}{feed:>7}{img:>34}")

    drift = [
        (r, p.existing_og_title(), p.title)
        for r, p in pages.items()
        if p.existing_og_title() and p.existing_og_title() != p.title
    ]
    missing_desc = [r for r, p in pages.items() if not p.description]

    # Connectivity, measured rather than assumed: how many notes are the
    # target of at least one read-next card.
    pointed_at = {c["rel"] for cards in plan.values() for c in cards}
    unpointed = sorted(set(plan) - pointed_at)

    print()
    print(f"sitemap:  {len(listed)} urls")
    print(f"feed:     {len(items)} items")
    print(f"read next: {len(plan)} notes × {READ_NEXT_COUNT} cards — "
          f"{len(pointed_at)}/{len(plan)} notes are linked from another note")
    if unpointed:
        print("  NOT POINTED AT BY ANY NOTE (the chronological cycle should "
              "make this impossible):")
        for r in unpointed:
            print(f"    · {r}")
    if orphans:
        print(f"\nPUBLISHED BUT NOT LINKED FROM THE SITE ({len(orphans)}) — left out of the")
        print("sitemap; listing them is a publishing decision, not this tool's:")
        for r in orphans:
            print(f"  · {r}")
    if drift:
        print("\nHAND-WRITTEN og:title DIFFERS FROM <title> (left alone, for a human):")
        for r, a, b in drift:
            print(f"  · {r}\n      og:title  {a}\n      <title>   {b}")
    if missing_desc:
        print(f"\nNO <meta name=description> — nothing to mirror ({len(missing_desc)}):")
        for r in missing_desc:
            print(f"  · {r}")

    # The pill is the seat's short lowercase tag (ara, claude, kevin, novak,
    # gemini). Measured 2026-10-24: 7 of 22 cards carry the full name instead,
    # so the card prints the name twice — once as a pill, once as the byline
    # directly beneath. Reported, not normalised: the cards are hand-written
    # and this tool does not rewrite a person's text. Fixing a card on
    # field/index.html propagates to every read-next block on the next --write.
    pill_drift = [
        (it["rel"], it["pill"]) for it in items
        if it["pill"] != it["pill"].strip().lower() or " " in it["pill"].strip()
    ]
    if pill_drift:
        print(f"\nVOICE-PILL IS NOT A SEAT TAG ({len(pill_drift)}) — the full name,"
              "\nso the name prints twice on every card; edit field/index.html:")
        for r, p in pill_drift:
            print(f"  · {r}   pill \"{p}\"")

    pending = page_changes + artefact_changes
    if not pending:
        print("\nnothing to do — the front door is already open.")
        return 0

    print(f"\npending: {len(page_changes)} pages, {len(artefact_changes)} files "
          f"({', '.join(artefact_changes) or 'none'})")

    if args.check:
        return 1

    for rel in page_changes:
        pages[rel].path.write_text(pages[rel].rendered(), encoding="utf-8")
    for name in artefact_changes:
        (SITE / name).write_text(artefacts[name], encoding="utf-8")
    print("written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Modules A, B and G: crawl and indexability, on-page, internal linking.

One code path serves a local build directory and a live site. What differs is
stated rather than hidden: a build directory has no server, so header-dependent
checks report as unavailable instead of passing.

Page facts are extracted once into a Page record, then the checks read that
record. Keeping extraction and judgement apart is what makes a second run of an
unchanged site produce identical findings.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser

import findings as F
from source import BuildSource, Response, Source, normalise

MAX_PAGES_DEFAULT = 500
TITLE_MIN, TITLE_MAX = 30, 60
DESC_MIN, DESC_MAX = 70, 160
IMAGE_MAX_BYTES = 200 * 1024
#: Images this early on a page are treated as above the fold and are
#: never reported for missing lazy loading.
EAGER_IMAGE_COUNT = 2
MAX_URL_LENGTH = 115
MAX_CLICK_DEPTH = 3
#: Sentinel for a page no internal link chain reaches from the homepage.
UNREACHABLE = 10**6
GENERIC_ANCHORS = {
    "click here", "read more", "more", "here", "link", "this", "learn more",
    "continue", "details", "download", "go", "see more",
}
SESSION_PARAMS = {"sessionid", "sid", "phpsessid", "jsessionid", "sessid"}
LEGACY_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"}
SOFT_404_MARKERS = re.compile(
    r"\b(page not found|404 not found|not found|no longer exists|page doesn't exist)\b",
    re.I,
)
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
#: Pages nothing should link to. A 404 page with no inbound links is
#: working as intended, so reporting it as an orphan is noise.
EXPECTED_UNLINKED = {"/404", "/404.html", "/_404", "/not-found"}


# ---------------------------------------------------------------------------
# Extraction


@dataclass
class Link:
    href: str
    resolved: str
    anchor: str
    internal: bool
    has_image_alt: bool = False


@dataclass
class Image:
    src: str
    resolved: str
    alt: str | None
    width: str | None
    height: str | None
    loading: str | None
    index: int


@dataclass
class Page:
    url: str
    status: int
    title: str | None = None
    description: str | None = None
    canonical: str | None = None
    robots_meta: str = ""
    x_robots_tag: str | None = None
    lang: str | None = None
    charset: str | None = None
    viewport: str | None = None
    headings: list[tuple[int, str]] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    og: dict[str, str] = field(default_factory=dict)
    twitter: dict[str, str] = field(default_factory=dict)
    jsonld_blocks: list[str] = field(default_factory=list)
    hreflang: list[tuple[str, str]] = field(default_factory=list)
    #: tel: hrefs, which is where a site declares a phone number.
    tel_links: list[str] = field(default_factory=list)
    text: str = ""
    word_count: int = 0
    body_hash: str = ""
    raw_bytes: int = 0
    has_scripts: bool = False
    error: str | None = None
    headers_available: bool = True

    @property
    def noindex(self) -> bool:
        directives = f"{self.robots_meta} {self.x_robots_tag or ''}".lower()
        return "noindex" in directives

    @property
    def indexable(self) -> bool:
        return self.status == 200 and not self.noindex

    @property
    def h1s(self) -> list[str]:
        return [text for level, text in self.headings if level == 1]


def extract(url: str, response: Response) -> Page:
    page = Page(
        url=url,
        status=response.status,
        error=response.error,
        headers_available=response.headers_available,
        raw_bytes=len(response.body),
    )
    if response.headers_available:
        page.x_robots_tag = response.headers.get("x-robots-tag")

    if not response.ok or not response.body:
        return page

    html = response.text()
    tree = HTMLParser(html)

    node = tree.css_first("title")
    if node is not None:
        page.title = node.text(strip=True)

    root = tree.css_first("html")
    if root is not None:
        page.lang = root.attributes.get("lang")

    for meta in tree.css("meta"):
        attrs = meta.attributes
        name = (attrs.get("name") or "").lower()
        prop = (attrs.get("property") or "").lower()
        content = attrs.get("content") or ""
        if "charset" in attrs:
            page.charset = attrs["charset"]
        elif (attrs.get("http-equiv") or "").lower() == "content-type" and "charset=" in content:
            page.charset = content.split("charset=", 1)[1].strip()
        if name == "description":
            page.description = content.strip()
        elif name == "robots":
            page.robots_meta = content
        elif name == "viewport":
            page.viewport = content
        elif prop.startswith("og:"):
            page.og[prop] = content
        elif name.startswith("twitter:"):
            page.twitter[name] = content

    for link in tree.css("link"):
        rel = (link.attributes.get("rel") or "").lower()
        href = link.attributes.get("href") or ""
        if rel == "canonical" and href:
            page.canonical = href.strip()
        elif rel == "alternate" and link.attributes.get("hreflang"):
            page.hreflang.append((link.attributes["hreflang"], href))

    for level in range(1, 7):
        for heading in tree.css(f"h{level}"):
            page.headings.append((level, heading.text(strip=True)))
    page.headings.sort(key=lambda item: html.find(item[1]) if item[1] else 0)

    for index, img in enumerate(tree.css("img")):
        attrs = img.attributes
        src = attrs.get("src") or attrs.get("data-src") or ""
        page.images.append(
            Image(
                src=src,
                resolved=urljoin(url, src) if src else "",
                alt=attrs.get("alt"),
                width=attrs.get("width"),
                height=attrs.get("height"),
                loading=attrs.get("loading"),
                index=index,
            )
        )

    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    for anchor in tree.css("a"):
        href = (anchor.attributes.get("href") or "").strip()
        if href.lower().startswith("tel:"):
            page.tel_links.append(href[4:])
            continue
        if not href or href.startswith(("mailto:", "javascript:", "#")):
            continue
        resolved = normalise(urljoin(url, href))
        page.links.append(
            Link(
                href=href,
                resolved=resolved,
                anchor=anchor.text(strip=True),
                internal=resolved.startswith(origin),
                has_image_alt=any(
                    (img.attributes.get("alt") or "").strip() for img in anchor.css("img")
                ),
            )
        )

    for script in tree.css("script"):
        script_type = (script.attributes.get("type") or "").lower()
        if script_type == "application/ld+json":
            page.jsonld_blocks.append(script.text())
        else:
            page.has_scripts = True

    for tag in tree.css("script, style, noscript, template"):
        tag.decompose()
    body = tree.css_first("body")
    page.text = (body.text(separator=" ", strip=True) if body else tree.text(strip=True)) or ""
    page.word_count = len(page.text.split())
    page.body_hash = hashlib.sha256(page.text.encode("utf-8")).hexdigest()
    return page


# ---------------------------------------------------------------------------
# Discovery


def sitemap_urls(src: Source, cfg) -> tuple[list[str], list[F.Finding]]:
    """Read the sitemap. Returns its URLs and any structural findings."""
    emitted: list[F.Finding] = []
    sitemap_url = src.absolute("/sitemap.xml")
    response = src.fetch("/sitemap.xml")

    if not response.ok:
        emitted.append(
            F.make("sitemap.missing", sitemap_url, f"/sitemap.xml returned {response.status}")
        )
        return [], emitted

    size = len(response.body)
    if size > 50 * 1024 * 1024:
        emitted.append(
            F.make("sitemap.too_large", sitemap_url, f"{size / 1024 / 1024:.1f} MB uncompressed")
        )

    try:
        root = ET.fromstring(response.body)
    except ET.ParseError as exc:
        emitted.append(F.make("sitemap.invalid_xml", sitemap_url, f"XML parse error: {exc}"))
        return [], emitted

    urls: list[str] = []
    lastmods: dict[str, str] = {}
    for entry in root.findall(".//sm:url", SITEMAP_NS) or root.findall(".//url"):
        loc = entry.find("sm:loc", SITEMAP_NS)
        if loc is None:
            loc = entry.find("loc")
        if loc is None or not loc.text:
            continue
        url = normalise(loc.text.strip())
        urls.append(url)
        lastmod = entry.find("sm:lastmod", SITEMAP_NS) or entry.find("lastmod")
        if lastmod is not None and lastmod.text:
            lastmods[url] = lastmod.text.strip()

    if len(urls) > 50_000:
        emitted.append(
            F.make("sitemap.too_many_urls", sitemap_url, f"{len(urls)} URLs in one file")
        )

    # Every entry sharing one timestamp means the generator used build time.
    if len(lastmods) > 2 and len(set(lastmods.values())) == 1:
        emitted.append(
            F.make(
                "sitemap.lastmod_is_build_time",
                sitemap_url,
                f"all {len(lastmods)} entries share lastmod {next(iter(lastmods.values()))}, "
                "which is the build timestamp rather than a content change date",
            )
        )

    return urls, emitted


def discover(src: Source, cfg, max_pages: int) -> list[str]:
    """URLs to crawl: build output when available, otherwise sitemap plus a walk."""
    if isinstance(src, BuildSource):
        return [url for url, _ in src.walk_pages()][:max_pages]

    seen: list[str] = [src.absolute("/")]
    queue = list(seen)
    index = 0
    while index < len(queue) and len(seen) < max_pages:
        current = queue[index]
        index += 1
        response = src.fetch(current)
        if not response.ok or not response.is_html:
            continue
        page = extract(current, response)
        for link in page.links:
            if link.internal and link.resolved not in seen and len(seen) < max_pages:
                seen.append(link.resolved)
                queue.append(link.resolved)
    return seen


# ---------------------------------------------------------------------------
# Checks


def check_page(page: Page, src: Source, emitted: list[F.Finding]) -> None:
    """Modules A and B for one page."""
    url = page.url

    if page.status == 0:
        return
    if 400 <= page.status < 500:
        emitted.append(F.make("http.status_4xx", url, f"returned {page.status}"))
        return
    if page.status >= 500:
        emitted.append(F.make("http.status_5xx", url, f"returned {page.status}"))
        return
    if page.status != 200:
        return

    # A noindexed error page returning 200 cannot be indexed, so it is not a
    # soft 404 in any sense that matters. Reporting it as an error sends people
    # to fix a page that is already handled correctly.
    if (
        page.text
        and not page.noindex
        and SOFT_404_MARKERS.search(page.text[:400])
        and page.word_count < 120
    ):
        emitted.append(
            F.make(
                "http.soft_404",
                url,
                f"returned 200 but the content reads as not-found: {page.text[:120]!r}",
            )
        )

    # -- indexability
    if page.canonical:
        canonical = page.canonical
        if not canonical.startswith(("http://", "https://")):
            emitted.append(
                F.make("canonical.not_absolute", url, f'canonical is "{canonical}"')
            )
        else:
            # Compare by served-URL key, not raw string: a host that serves
            # about.html at /about makes those two spellings the same page, and
            # comparing strings reports every correct canonical as wrong.
            if src.canonical_key(canonical) != src.canonical_key(url):
                emitted.append(
                    F.make(
                        "canonical.not_self_referencing",
                        url,
                        f"canonical points at {canonical}",
                        group=canonical,
                    )
                )
            target = src.fetch(canonical)
            if target.status == 0 and target.error:
                pass  # external or unreachable: not evidence of a broken canonical
            elif not target.ok:
                emitted.append(
                    F.make(
                        "canonical.target_not_200",
                        url,
                        f"canonical {canonical} returned {target.status}",
                    )
                )
    else:
        emitted.append(F.make("canonical.missing", url, "no rel=canonical link element"))

    # -- URL shape
    path = urlparse(url).path
    if any(character.isupper() for character in path):
        emitted.append(F.make("url.uppercase", url, f"path contains uppercase: {path}"))
    if " " in path or "%20" in path:
        emitted.append(F.make("url.spaces", url, f"path contains a space: {path}"))
    query = urlparse(url).query.lower()
    for parameter in SESSION_PARAMS:
        if f"{parameter}=" in query:
            emitted.append(F.make("url.session_parameter", url, f"query contains {parameter}="))
            break
    if len(url) > MAX_URL_LENGTH:
        emitted.append(F.make("url.excessive_length", url, f"{len(url)} characters"))

    # -- on-page, module B
    if not page.title:
        emitted.append(F.make("title.missing", url, "no title element, or it is empty"))
    else:
        length = len(page.title)
        if length < TITLE_MIN:
            emitted.append(
                F.make("title.too_short", url, f"{length} characters: {page.title!r}")
            )
        elif length > TITLE_MAX:
            emitted.append(
                F.make("title.too_long", url, f"{length} characters: {page.title[:70]!r}...")
            )

    if not page.description:
        emitted.append(F.make("meta_description.missing", url, "no meta description"))
    else:
        length = len(page.description)
        if length < DESC_MIN:
            emitted.append(
                F.make("meta_description.too_short", url, f"{length} characters")
            )
        elif length > DESC_MAX:
            emitted.append(F.make("meta_description.too_long", url, f"{length} characters"))

    h1s = page.h1s
    if not h1s:
        emitted.append(F.make("heading.h1_missing", url, "no h1 element"))
    elif len(h1s) > 1:
        emitted.append(
            F.make("heading.h1_multiple", url, f"{len(h1s)} h1 elements: {h1s[:3]}")
        )

    previous = 0
    for level, text in page.headings:
        if previous and level > previous + 1:
            emitted.append(
                F.make(
                    "heading.level_skipped",
                    url,
                    f"h{previous} is followed by h{level}: {text[:60]!r}",
                )
            )
            break
        previous = level

    if page.lang is None:
        emitted.append(F.make("html.lang_missing", url, "html element has no lang attribute"))
    if page.viewport is None:
        emitted.append(F.make("html.viewport_missing", url, "no viewport meta tag"))
    if page.charset is None:
        emitted.append(F.make("html.charset_missing", url, "no charset declaration"))

    # -- images
    for image in page.images:
        if image.alt is None:
            emitted.append(
                F.make("image.alt_missing", url, f"<img src={image.src!r}> has no alt attribute")
            )
        if not image.width or not image.height:
            emitted.append(
                F.make(
                    "image.dimensions_missing",
                    url,
                    f"<img src={image.src!r}> has no width and height",
                )
            )
        # The first images on a page are usually above the fold, and one of them
        # is the largest contentful paint element. Lazy-loading those makes the
        # metric this check exists to protect worse, so they are spared. A site
        # with a header logo followed by hero artwork has two before any content
        # image, which is the common shape.
        if image.index >= EAGER_IMAGE_COUNT and (image.loading or "").lower() != "lazy":
            emitted.append(
                F.make("image.no_lazy_loading", url, f"{image.src} is below the fold and eager")
            )
        if isinstance(src, BuildSource) and image.resolved:
            local = src.local_path(image.resolved)
            if local is not None:
                size = local.stat().st_size
                if size > IMAGE_MAX_BYTES:
                    emitted.append(
                        F.make(
                            "image.oversized",
                            url,
                            f"{image.src} is {size / 1024:.0f} KB",
                        )
                    )
                if local.suffix.lower() in LEGACY_IMAGE_SUFFIXES and size > 40 * 1024:
                    emitted.append(
                        F.make(
                            "image.legacy_format",
                            url,
                            f"{image.src} is {local.suffix} at {size / 1024:.0f} KB",
                        )
                    )

    # -- social
    if not page.og.get("og:title") and not page.og.get("og:image"):
        emitted.append(F.make("social.og_missing", url, "no Open Graph tags"))
    elif page.og.get("og:image") and src.is_internal(page.og["og:image"]):
        target = src.fetch(page.og["og:image"])
        if not target.ok:
            emitted.append(
                F.make(
                    "social.og_image_not_200",
                    url,
                    f"og:image {page.og['og:image']} returned {target.status}",
                )
            )
    if not page.twitter.get("twitter:card"):
        emitted.append(F.make("social.twitter_card_missing", url, "no twitter:card tag"))

    # -- anchors
    for link in page.links:
        anchor = link.anchor.strip()
        if not anchor and not link.has_image_alt:
            emitted.append(
                F.make("anchor.empty", url, f"link to {link.href} has no text and no image alt")
            )
        elif anchor.lower() in GENERIC_ANCHORS:
            emitted.append(
                F.make("anchor.generic", url, f'anchor text "{anchor}" links to {link.href}')
            )

    if page.word_count and page.word_count < 150:
        emitted.append(F.make("content.thin", url, f"{page.word_count} words of body text"))

    if not page.jsonld_blocks:
        emitted.append(F.make("schema.none_found", url, "no JSON-LD blocks on the page"))

    # -- rendering. Raw HTML is what AI crawlers read.
    if page.has_scripts and page.word_count < 60:
        emitted.append(
            F.make(
                "render.content_requires_javascript",
                url,
                f"raw HTML carries only {page.word_count} words of text alongside script tags, "
                "so the main content is probably assembled in the browser",
            )
        )
        emitted.append(
            F.make(
                "ai.content_requires_javascript",
                url,
                f"raw HTML carries only {page.word_count} words of text; AI crawlers read this "
                "response and do not run scripts",
            )
        )


def check_site(pages: dict[str, Page], sitemap: list[str], src: Source, cfg,
               emitted: list[F.Finding]) -> dict:
    """Cross-page checks: duplicates, orphans, depth, sitemap agreement."""
    live_pages = {url: page for url, page in pages.items() if page.status == 200}

    by_title: dict[str, list[str]] = {}
    by_description: dict[str, list[str]] = {}
    by_hash: dict[str, list[str]] = {}
    for url, page in live_pages.items():
        if page.title:
            by_title.setdefault(page.title, []).append(url)
        if page.description:
            by_description.setdefault(page.description, []).append(url)
        if page.body_hash:
            by_hash.setdefault(page.body_hash, []).append(url)

    for title, urls in by_title.items():
        if len(urls) > 1:
            emitted.append(
                F.make("duplicate.title", urls, f"{len(urls)} pages share the title {title!r}",
                       group=title[:60])
            )
    for description, urls in by_description.items():
        if len(urls) > 1:
            emitted.append(
                F.make(
                    "duplicate.meta_description",
                    urls,
                    f"{len(urls)} pages share the same meta description",
                    group=description[:60],
                )
            )
    for digest, urls in by_hash.items():
        if len(urls) > 1:
            emitted.append(
                F.make(
                    "duplicate.identical_content",
                    urls,
                    f"{len(urls)} URLs serve identical body text (sha256 {digest[:12]})",
                    group=digest[:12],
                )
            )

    # Internal link graph.
    # Everything below compares pages by the URL the host serves, so /about,
    # /about.html and /about/ count as one page rather than three.
    key_of = {url: src.canonical_key(url) for url in live_pages}
    by_key = {key: url for url, key in key_of.items()}

    inbound: dict[str, set[str]] = {url: set() for url in live_pages}
    anchors: dict[str, list[str]] = {url: [] for url in live_pages}
    for url, page in live_pages.items():
        for link in page.links:
            target_key = src.canonical_key(link.resolved)
            target = by_key.get(target_key, link.resolved)
            if target in inbound and target != url:
                inbound[target].add(url)
                anchors[target].append(link.anchor.strip().lower())
            elif link.internal and target_key not in by_key:
                response = src.fetch(link.resolved)
                target = link.resolved
                if not response.ok:
                    emitted.append(
                        F.make(
                            "http.status_4xx" if response.status < 500 else "http.status_5xx",
                            target,
                            f"linked from {url}, returned {response.status}",
                        )
                    )

    home = src.absolute("/")
    home = by_key.get(src.canonical_key(home), home)
    depth = _depths(home, live_pages, src)

    for url, sources in inbound.items():
        if url == home:
            continue
        if urlparse(url).path.rstrip("/").lower() in EXPECTED_UNLINKED:
            continue
        # A page that tells search engines not to index it is not asking to be
        # found, so having no inbound link is the intended state. Confirmation
        # and thank-you pages are the usual case: they are reached by doing
        # something, never by following a link.
        page = live_pages.get(url)
        if page is not None and page.noindex:
            continue
        if not sources:
            emitted.append(F.make("links.no_inbound", url, "no internal link points at this page"))
        elif len(sources) == 1:
            emitted.append(
                F.make("links.single_inbound", url, f"only {next(iter(sources))} links here")
            )
        unique_anchors = {a for a in anchors.get(url, []) if a}
        if len(sources) >= 3 and len(unique_anchors) == 1:
            emitted.append(
                F.make(
                    "links.anchor_monotony",
                    url,
                    f"all {len(sources)} inbound links use the anchor {next(iter(unique_anchors))!r}",
                )
            )

    for url, distance in depth.items():
        # UNREACHABLE pages are already reported as orphans. Reporting them as
        # deep as well would be the same problem counted twice.
        if distance == UNREACHABLE:
            continue
        if distance > MAX_CLICK_DEPTH:
            emitted.append(
                F.make("structure.deep_page", url, f"{distance} clicks from the homepage")
            )

    # Sitemap agreement.
    sitemap_set = {normalise(url) for url in sitemap}
    for listed in sorted(sitemap_set):
        # Match the sitemap's spelling to the page we actually walked.
        url = by_key.get(src.canonical_key(listed), listed)
        page = pages.get(url)
        if page is None:
            response = src.fetch(url)
            if not response.ok:
                emitted.append(
                    F.make(
                        "sitemap.contains_non_200",
                        url,
                        f"listed in the sitemap, returned {response.status}",
                    )
                )
                continue
            page = extract(url, response)
            pages[url] = page
        if page.status != 200:
            emitted.append(
                F.make(
                    "sitemap.contains_non_200",
                    url,
                    f"listed in the sitemap, returned {page.status}",
                )
            )
            continue
        if page.noindex:
            emitted.append(
                F.make(
                    "index.noindex_in_sitemap",
                    url,
                    f"listed in the sitemap while carrying robots {page.robots_meta!r}",
                )
            )
        if page.canonical and normalise(page.canonical) != url:
            emitted.append(
                F.make(
                    "sitemap.contains_noncanonical",
                    url,
                    f"sitemap lists this URL but its canonical is {page.canonical}",
                )
            )
        if not inbound.get(url) and not page.noindex:
            emitted.append(
                F.make(
                    "structure.orphan_url",
                    url,
                    "in the sitemap with no internal link pointing at it",
                )
            )

    # noindex pages that navigation still links to.
    for url, page in live_pages.items():
        if page.noindex and inbound.get(url):
            emitted.append(
                F.make(
                    "index.noindex_but_linked",
                    url,
                    f"carries robots {page.robots_meta!r} and is linked from "
                    f"{len(inbound[url])} page(s)",
                )
            )

    return {
        "pages_crawled": len(pages),
        "pages_200": len(live_pages),
        "sitemap_urls": len(sitemap_set),
        "max_depth": max(depth.values()) if depth else 0,
        "headers_available": src.headers_available,
    }


def _depths(home: str, pages: dict[str, Page], src: Source) -> dict[str, int]:
    """Clicks from the homepage, following links by served-URL key.

    A link to /about must reach the page walked as about.html, or every page
    looks unreachable and the whole site reports as orphaned.
    """
    by_key = {src.canonical_key(url): url for url in pages}

    distances = {home: 0}
    frontier = [home]
    while frontier:
        nxt = []
        for url in frontier:
            page = pages.get(url)
            if page is None:
                continue
            for link in page.links:
                target = by_key.get(src.canonical_key(link.resolved))
                if target is not None and target not in distances:
                    distances[target] = distances[url] + 1
                    nxt.append(target)
        frontier = nxt
    for url in pages:
        distances.setdefault(url, UNREACHABLE)
    return distances


# ---------------------------------------------------------------------------
# Entry point


def run(cfg, *, live: bool = False, max_pages: int = MAX_PAGES_DEFAULT) -> dict:
    from source import open_source

    src = open_source(cfg, live=live)
    emitted: list[F.Finding] = []
    try:
        sitemap, sitemap_findings = sitemap_urls(src, cfg)
        emitted.extend(sitemap_findings)

        urls = discover(src, cfg, max_pages)
        pages: dict[str, Page] = {}
        for url in urls:
            response = src.fetch(url)
            page = extract(url, response)
            pages[url] = page
            check_page(page, src, emitted)

        stats = check_site(pages, sitemap, src, cfg, emitted)
    finally:
        src.close()

    merged = F.order(F.merge(emitted))
    return {
        "modules": ["A", "B", "G"],
        "site": cfg.site,
        "source": src.label,
        "source_kind": "build" if isinstance(src, BuildSource) else "live",
        "stats": stats,
        "findings": [f.to_dict() for f in merged],
        "notes": (
            []
            if src.headers_available
            else [
                "Auditing build output, so response headers do not exist. "
                "X-Robots-Tag, compression, cache and redirect checks report as "
                "unavailable rather than passing. Run with --live against the "
                "deployed site to cover them."
            ]
        ),
    }


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Modules A, B and G: crawl, on-page, linking")
    parser.add_argument("--live", action="store_true", help="crawl the deployed site over HTTP")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_DEFAULT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = run(cfg, live=args.live, max_pages=args.max_pages)

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    stats = result["stats"]
    print(f"Crawled {stats['pages_crawled']} URLs from {result['source']}")
    print(f"  {stats['pages_200']} returned 200, sitemap lists {stats['sitemap_urls']}")
    print()
    counts: dict[str, int] = {}
    for finding in result["findings"]:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    print(
        f"{counts.get('error', 0)} errors, {counts.get('warning', 0)} warnings, "
        f"{counts.get('notice', 0)} notices"
    )
    print()
    for finding in result["findings"]:
        urls = finding["urls"]
        where = urls[0] if len(urls) == 1 else f"{len(urls)} URLs"
        print(f"  [{finding['severity']:7s}] {finding['id']:38s} {where}")
        print(f"            {finding['evidence'][:150]}")
    for note in result["notes"]:
        print(f"\nNote: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

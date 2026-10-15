"""Find the site's own logo so its reports carry its branding.

A report is read by the people who own the site, and often handed on to a
client or a manager. It should look like theirs. siteseo looks for the logo the
way a person would, in this order:

1. `report_logo` in siteseo.yaml, a path inside the site repository.
2. The `logo` the homepage declares in its structured data, usually on an
   Organization or LocalBusiness block.
3. An image in the homepage whose class, id, alt text or file name says logo,
   preferring one inside the page header.
4. The site icon: an SVG icon first, then the Apple touch icon.

Nothing here fails a run. A site with no findable logo gets a report without
one.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser

MIME_BY_SUFFIX = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".avif": "image/avif",
}
MAX_BYTES = 2 * 1024 * 1024


@dataclass
class Logo:
    data: bytes
    mime: str
    #: How it was found, for the report's footnote and for debugging.
    found_by: str
    #: A file inside the site repository, when the logo is one.
    file: Path | None = None
    #: The logo's address on the site, when it came from a page.
    url: str | None = None

    def data_uri(self) -> str:
        return f"data:{self.mime};base64,{base64.b64encode(self.data).decode('ascii')}"

    def markdown_target(self, from_dir: Path) -> str | None:
        """What a Markdown report saved in `from_dir` should point at."""
        if self.file is not None:
            return Path(os.path.relpath(self.file, from_dir)).as_posix()
        return self.url


def _mime(name: str, body: bytes, content_type: str = "") -> str | None:
    ctype = content_type.split(";")[0].strip().lower()
    if ctype.startswith("image/") and ctype != "image/x-icon":
        return ctype
    suffix = Path(urlparse(name).path).suffix.lower()
    if suffix in MIME_BY_SUFFIX:
        return MIME_BY_SUFFIX[suffix]
    if body.lstrip()[:5].lower() in (b"<svg ", b"<?xml"):
        return "image/svg+xml"
    return None


def from_config(cfg) -> Logo | None:
    if not getattr(cfg, "report_logo", None):
        return None
    path = (cfg.root / cfg.report_logo).resolve()
    if not path.is_file():
        return None
    body = path.read_bytes()
    mime = _mime(path.name, body)
    if mime is None or len(body) > MAX_BYTES:
        return None
    return Logo(body, mime, "report_logo in siteseo.yaml", file=path)


def _schema_logos(tree: HTMLParser) -> list[str]:
    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            logo = node.get("logo")
            if isinstance(logo, str):
                found.append(logo)
            elif isinstance(logo, dict):
                found.extend(v for v in (logo.get("url"), logo.get("contentUrl")) if isinstance(v, str))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for script in tree.css('script[type="application/ld+json"]'):
        try:
            walk(json.loads(script.text() or ""))
        except ValueError:
            continue
    return found


def _img_logos(tree: HTMLParser) -> list[str]:
    def says_logo(img) -> bool:
        attrs = img.attributes
        text = " ".join(str(attrs.get(k) or "") for k in ("class", "id", "alt", "src")).lower()
        parent = img.parent
        for _ in range(3):
            if parent is None:
                break
            text += " " + " ".join(str(parent.attributes.get(k) or "") for k in ("class", "id")).lower()
            parent = parent.parent
        return "logo" in text

    in_header = [img for img in tree.css("header img") if img.attributes.get("src")]
    tagged = [img for img in tree.css("img") if img.attributes.get("src") and says_logo(img)]
    ordered = [img for img in in_header if says_logo(img)] + tagged + in_header
    return [img.attributes["src"] for img in ordered]


def _icon_logos(tree: HTMLParser) -> list[str]:
    svg = [n.attributes.get("href") for n in tree.css('link[rel~="icon"]')
           if (n.attributes.get("type") or "").endswith("svg+xml")
           or str(n.attributes.get("href") or "").lower().endswith(".svg")]
    touch = [n.attributes.get("href") for n in tree.css('link[rel="apple-touch-icon"]')]
    return [href for href in svg + touch if href]


def from_site(cfg, src) -> Logo | None:
    home = cfg.site.rstrip("/") + "/"
    try:
        response = src.fetch(home)
    except Exception:  # noqa: BLE001 - a missing logo never fails a run
        return None
    if not response.ok or not response.body:
        return None
    tree = HTMLParser(response.text())

    for found_by, candidates in (
        ("the logo in the homepage's structured data", _schema_logos(tree)),
        ("a logo image on the homepage", _img_logos(tree)),
        ("the site icon", _icon_logos(tree)),
    ):
        for candidate in candidates:
            url = urljoin(response.final_url, candidate.strip())
            try:
                image = src.fetch(url)
            except Exception:  # noqa: BLE001
                continue
            if not image.ok or not image.body or len(image.body) > MAX_BYTES:
                continue
            mime = _mime(url, image.body, image.headers.get("content-type", ""))
            if mime is None:
                continue
            file = None
            root = getattr(src, "root", None)
            if root is not None:
                local = Path(root) / urlparse(url).path.lstrip("/")
                if local.is_file():
                    file = local.resolve()
            return Logo(image.body, mime, found_by, file=file, url=url)
    return None


def find(cfg) -> Logo | None:
    """The site's logo, or None. Never raises."""
    logo = from_config(cfg)
    if logo is not None:
        return logo
    try:
        from source import open_source

        with open_source(cfg) as src:
            return from_site(cfg, src)
    except Exception:  # noqa: BLE001
        return None

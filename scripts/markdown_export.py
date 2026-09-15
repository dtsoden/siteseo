"""Markdown for agents, built from your own pages at no cost.

Cloudflare's Markdown for Agents converts HTML at its edge when a request sends
`Accept: text/markdown`, on the Pro plan and above. This does the same work at
build time instead. It reads the built HTML, keeps the main content, and writes
a `.md` file next to each page:

    index.html        ->  index.md
    about/index.html  ->  about/index.md
    blog.html         ->  blog.md

Each file opens with frontmatter (title, description, canonical URL, image) and
closes with the page's JSON-LD, the same shape Cloudflare produces, so an agent
gets the same document whichever route made it.

Two rules shape it:

  1. It runs after every build. The Markdown is derived from built HTML, so it
     belongs in the build script, the way a sitemap generator does. Committing
     the output once would leave it stale after the next change.
  2. It never rewrites words. The Markdown carries the page's own text, which is
     why this is a build step rather than content work, and why it never
     touches a `.md` file it did not write.

Writing the files is half the job. Plain files cannot answer an Accept header,
so `--setup` generates the rule that does for your host, shown as a diff and
written only with `--apply`.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser, Node

from source import BuildSource

#: Marks a file this tool wrote. Only files carrying it are ever overwritten or
#: removed, so a hand-written .md in the build is safe.
MARKER = "generator: siteseo"
LINK_TYPE = "text/markdown"

#: Pages nothing should hand to an agent.
SKIP_PATHS = {"/404", "/404.html", "/_404", "/not-found"}

#: Removed wherever they appear. None of them carry the page's content.
DROP = (
    "script, style, noscript, template, svg, canvas, iframe, object, embed, "
    "button, input, select, textarea, dialog, nav, [hidden], [aria-hidden=true]"
)
#: Removed only when there is no <main> or <article> to take content from, and
#: then only outside an article, where they are site chrome rather than content.
CHROME = ("header", "footer", "aside")

BLOCK = {
    "address", "article", "aside", "body", "details", "div", "fieldset", "figure",
    "footer", "header", "hgroup", "main", "section", "summary", "center",
}
HEADINGS = {f"h{n}": n for n in range(1, 7)}
INLINE_WRAP = {"strong": "**", "b": "**", "em": "*", "i": "*", "del": "~~", "s": "~~"}
SPACE = re.compile(r"\s+")
ESCAPE = re.compile(r"([\\`*\[\]])")


# ---------------------------------------------------------------------------
# Conversion


@dataclass
class Page:
    source: Path
    url: str
    title: str = ""
    description: str = ""
    canonical: str = ""
    image: str = ""
    lang: str = ""
    noindex: bool = False
    refresh: bool = False
    markdown: str = ""
    jsonld: list = field(default_factory=list)


class Converter:
    """HTML to Markdown for one page, with every URL made absolute.

    Absolute URLs matter because the Markdown is fetched on its own, often at a
    different path from the page, and relative links would resolve wrongly.
    """

    def __init__(self, base_url: str):
        self.base = base_url

    def convert(self, root: Node) -> str:
        text = self.blocks(root)
        text = re.sub(r"[ \t]+\n", lambda m: "  \n" if m.group(0).startswith("  ") else "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"

    # -- blocks

    def blocks(self, node: Node) -> str:
        out: list[str] = []
        inline: list[str] = []

        def flush() -> None:
            joined = SPACE.sub(" ", "".join(inline)).strip()
            joined = joined.replace(" ", "  \n").replace("", "  \n")
            if joined:
                out.append(joined)
            inline.clear()

        for child in _children(node):
            tag = child.tag
            if tag == "-text" or not self.is_block(child):
                inline.append(self.inline(child))
                continue
            flush()
            rendered = self.block(child)
            if rendered.strip():
                out.append(rendered.strip("\n"))
        flush()
        return "\n\n".join(out)

    def is_block(self, node: Node) -> bool:
        return node.tag in BLOCK or node.tag in HEADINGS or node.tag in {
            "p", "ul", "ol", "pre", "blockquote", "table", "hr", "dl", "figcaption",
            "audio", "video",
        }

    def block(self, node: Node) -> str:
        tag = node.tag
        if tag in HEADINGS:
            text = self.inline_children(node)
            return f"{'#' * HEADINGS[tag]} {text}" if text else ""
        if tag == "p" or tag == "figcaption":
            return self.inline_children(node)
        if tag in {"ul", "ol"}:
            return self.list(node)
        if tag == "pre":
            return self.pre(node)
        if tag == "blockquote":
            inner = self.blocks(node)
            return "\n".join(f"> {line}" if line else ">" for line in inner.splitlines())
        if tag == "table":
            return self.table(node)
        if tag == "hr":
            return "---"
        if tag == "dl":
            return self.definitions(node)
        if tag in {"audio", "video"}:
            return self.media(node)
        return self.blocks(node)

    def list(self, node: Node, depth: int = 0) -> str:
        ordered = node.tag == "ol"
        try:
            number = int(node.attributes.get("start") or 1)
        except ValueError:
            number = 1
        lines: list[str] = []
        indent = "   " * depth if ordered else "  " * depth
        for item in _children(node):
            if item.tag != "li":
                continue
            marker = f"{number}." if ordered else "-"
            number += 1
            text_parts: list[str] = []
            nested: list[str] = []
            for child in _children(item):
                if child.tag in {"ul", "ol"}:
                    nested.append(self.list(child, depth + 1))
                elif child.tag != "-text" and self.is_block(child):
                    text_parts.append(" " + self.block(child).replace("\n", " ") + " ")
                else:
                    text_parts.append(self.inline(child))
            text = SPACE.sub(" ", "".join(text_parts)).strip().replace("", "  \n")
            lines.append(f"{indent}{marker} {text}".rstrip())
            lines.extend(nested)
        return "\n".join(lines)

    def pre(self, node: Node) -> str:
        code = node.css_first("code")
        classes = ((code.attributes.get("class") if code else None) or
                   node.attributes.get("class") or "")
        match = re.search(r"(?:language|lang)-([\w+#-]+)", classes)
        body = node.text(deep=True).strip("\n")
        fence = "```"
        while fence in body:
            fence += "`"
        return f"{fence}{match.group(1) if match else ''}\n{body}\n{fence}"

    def table(self, node: Node) -> str:
        rows = []
        for row in node.css("tr"):
            cells = [
                self.inline_children(cell).replace("|", "\\|")
                for cell in _children(row) if cell.tag in {"td", "th"}
            ]
            if cells:
                rows.append(cells)
        if not rows:
            return ""
        width = max(len(row) for row in rows)
        rows = [row + [""] * (width - len(row)) for row in rows]
        lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
        lines += ["| " + " | ".join(row) + " |" for row in rows[1:]]
        return "\n".join(lines)

    def definitions(self, node: Node) -> str:
        parts = []
        for child in _children(node):
            if child.tag == "dt":
                parts.append(f"**{self.inline_children(child)}**")
            elif child.tag == "dd":
                parts.append(self.inline_children(child))
        return "\n\n".join(p for p in parts if p.strip("*"))

    def media(self, node: Node) -> str:
        src = node.attributes.get("src")
        if not src:
            source = node.css_first("source")
            src = source.attributes.get("src") if source else None
        if not src:
            return ""
        label = node.attributes.get("title") or node.attributes.get("aria-label") or node.tag.title()
        return f"[{_escape(label)}]({self.absolute(src)})"

    # -- inline

    def inline_children(self, node: Node) -> str:
        text = "".join(self.inline(child) for child in _children(node))
        return SPACE.sub(" ", text).strip().replace(" ", "  \n").replace("", "  \n")

    def inline(self, node: Node) -> str:
        tag = node.tag
        if tag == "-text":
            return _escape(node.text(deep=False))
        if tag == "br":
            return ""
        if tag in INLINE_WRAP:
            inner = self.inline_children(node)
            mark = INLINE_WRAP[tag]
            return f"{mark}{inner}{mark}" if inner else ""
        if tag == "code":
            code = SPACE.sub(" ", node.text(deep=True))
            fence = "``" if "`" in code else "`"
            return f"{fence}{code}{fence}" if code.strip() else ""
        if tag == "a":
            return self.link(node)
        if tag == "img":
            return self.image(node)
        if self.is_block(node):
            return " " + self.block(node).replace("\n", " ") + " "
        return "".join(self.inline(child) for child in _children(node))

    def link(self, node: Node) -> str:
        href = (node.attributes.get("href") or "").strip()
        text = self.inline_children(node)
        if not href or href.lower().startswith("javascript:"):
            return text
        target = href if href.startswith(("mailto:", "tel:")) else self.absolute(href)
        if not text:
            return ""
        if text == target:
            return f"<{target}>"
        return f"[{text}]({target})"

    def image(self, node: Node) -> str:
        src = (node.attributes.get("src") or node.attributes.get("data-src") or "").strip()
        if not src or src.startswith("data:"):
            return ""
        alt = _escape(SPACE.sub(" ", node.attributes.get("alt") or "").strip())
        return f"![{alt}]({self.absolute(src)})"

    def absolute(self, href: str) -> str:
        return urljoin(self.base, href).replace(" ", "%20").replace(")", "%29")


def _children(node: Node):
    child = node.child
    while child is not None:
        yield child
        child = child.next


def _escape(text: str) -> str:
    text = ESCAPE.sub(r"\\\1", text or "")
    # An underscore inside a word never starts emphasis, so only escape the ones
    # at a word edge. Escaping every snake_case name hurts readability for nothing.
    return re.sub(r"(?<!\w)_|_(?!\w)", r"\\_", text)


def _has_ancestor(node: Node, tags: set[str]) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.tag in tags:
            return True
        parent = parent.parent
    return False


def extract(path: Path, url: str) -> Page:
    """Read one built page and convert its main content."""
    html = path.read_text(encoding="utf-8", errors="replace")
    tree = HTMLParser(html)
    page = Page(source=path, url=url)

    title = tree.css_first("title")
    page.title = title.text(strip=True) if title else ""
    root = tree.css_first("html")
    page.lang = (root.attributes.get("lang") or "") if root else ""

    for meta in tree.css("meta"):
        attrs = meta.attributes
        name = (attrs.get("name") or attrs.get("property") or "").lower()
        content = (attrs.get("content") or "").strip()
        if name == "description":
            page.description = content
        elif name == "robots" and "noindex" in content.lower():
            page.noindex = True
        elif name == "og:image" and content:
            page.image = urljoin(url, content)
        elif (attrs.get("http-equiv") or "").lower() == "refresh":
            page.refresh = True
    for link in tree.css("link"):
        rel = (link.attributes.get("rel") or "").lower().split()
        if "canonical" in rel and link.attributes.get("href"):
            page.canonical = urljoin(url, link.attributes["href"].strip())
    for script in tree.css('script[type="application/ld+json"]'):
        try:
            page.jsonld.append(json.loads(script.text()))
        except ValueError:
            continue

    for node in tree.css(DROP):
        node.decompose()

    content = tree.css_first("main") or tree.css_first('[role="main"]')
    articles = tree.css("article")
    if content is None and len(articles) == 1:
        content = articles[0]
    if content is None:
        content = tree.body or tree.root
        for node in tree.css(", ".join(CHROME)):
            if not _has_ancestor(node, {"article", "main"}):
                node.decompose()

    base = page.canonical or url
    body = Converter(base).convert(content) if content is not None else ""
    if page.title and not re.search(r"^# ", body, re.M):
        body = f"# {_escape(page.title)}\n\n{body}"
    page.markdown = body
    return page


def render(page: Page) -> str:
    meta = [("title", page.title), ("description", page.description),
            ("url", page.canonical or page.url), ("image", page.image), ("lang", page.lang)]
    lines = ["---"]
    for key, value in meta:
        if value:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines += [MARKER, "---", "", page.markdown.rstrip()]
    for block in page.jsonld:
        lines += ["", "```json", json.dumps(block, indent=2, ensure_ascii=False), "```"]
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# The build step


@dataclass
class Result:
    written: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    linked: list[str] = field(default_factory=list)
    llms_txt: str = ""

    def to_dict(self) -> dict:
        return {
            "written": self.written, "unchanged": self.unchanged,
            "skipped": [{"path": p, "reason": r} for p, r in self.skipped],
            "removed": self.removed, "linked": self.linked, "llms_txt": self.llms_txt,
        }


def markdown_path(html_path: Path) -> Path:
    return html_path.with_suffix(".md")


def generated_by_us(path: Path) -> bool:
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return False
    return head.startswith("---") and MARKER in head.split("\n---", 1)[0]


def export(cfg, *, link_tags: bool = True, llms_txt: bool = False) -> Result:
    """Write a .md next to every page in the build and link each page to it."""
    build = cfg.build_path
    if build is None or not build.is_dir():
        raise FileNotFoundError(
            f"build_dir {build} does not exist. Build the site first, then run this."
        )
    src = BuildSource(build, cfg.origin)
    result = Result()
    expected: set[Path] = set()
    exported: list[tuple[str, Page, str]] = []

    for url, path in src.walk_pages():
        rel = path.relative_to(build).as_posix()
        if urlparse(url).path.rstrip("/").lower() in SKIP_PATHS:
            result.skipped.append((rel, "error page"))
            continue
        page = extract(path, url)
        if page.noindex:
            result.skipped.append((rel, "carries noindex"))
            continue
        if page.refresh:
            result.skipped.append((rel, "meta refresh redirect"))
            continue

        target = markdown_path(path)
        target_rel = target.relative_to(build).as_posix()
        if target.exists() and not generated_by_us(target):
            result.skipped.append((rel, f"{target_rel} exists and was not written by siteseo"))
            continue

        expected.add(target)
        exported.append((url, page, "/" + target_rel))
        text = render(page)
        if target.exists() and target.read_text(encoding="utf-8") == text:
            result.unchanged.append(target_rel)
        else:
            target.write_bytes(text.encode("utf-8"))
            result.written.append(target_rel)

        if link_tags and add_link_tag(path, "/" + target_rel):
            result.linked.append(rel)

    for md in sorted(build.rglob("*.md")):
        if md not in expected and generated_by_us(md):
            md.unlink()
            result.removed.append(md.relative_to(build).as_posix())

    if llms_txt:
        result.llms_txt = write_llms_txt(cfg, build, exported)
    return result


LLMS_MARKER = "<!-- generator: siteseo -->"


def write_llms_txt(cfg, build: Path, exported: list[tuple[str, Page, str]]) -> str:
    """An index of every exported page in the llms.txt layout.

    llms.txt is a community proposal (llmstxt.org), not a standard. Google says
    Search ignores it, and Cloudflare's scanner no longer checks for it. It is
    here because it is the one index format agents that do look for Markdown
    recognise, and producing it costs nothing once the Markdown exists.
    """
    target = build / "llms.txt"
    if target.exists() and LLMS_MARKER not in target.read_text(encoding="utf-8", errors="replace"):
        return "skipped: llms.txt exists and was not written by siteseo"

    home = next((page for url, page, _ in exported if urlparse(url).path in {"", "/"}), None)
    name = (home.title if home and home.title else urlparse(cfg.origin).netloc)
    lines = [f"# {name}", ""]
    if home and home.description:
        lines += [f"> {home.description}", ""]
    lines += ["## Pages", ""]
    for url, page, href in sorted(exported, key=lambda item: urlparse(item[0]).path):
        label = _escape(page.title or urlparse(url).path)
        entry = f"- [{label}]({cfg.origin}{href})"
        lines.append(f"{entry}: {page.description}" if page.description else entry)
    lines += ["", LLMS_MARKER]
    text = "\n".join(lines) + "\n"

    if target.exists() and target.read_text(encoding="utf-8") == text:
        return "unchanged"
    target.write_bytes(text.encode("utf-8"))
    return "written"


LINK_TAG = re.compile(r"<link\b[^>]*type\s*=\s*[\"']?text/markdown", re.I)
HEAD_CLOSE = re.compile(r"</head\s*>", re.I)


def add_link_tag(path: Path, href: str) -> bool:
    """Point the page at its Markdown with <link rel="alternate">. Idempotent.

    An agent that never sends an Accept header can still find the Markdown this
    way. Returns True when the file changed.
    """
    raw = path.read_bytes()
    try:
        html = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if LINK_TAG.search(html):
        return False
    match = HEAD_CLOSE.search(html)
    if not match:
        return False
    tag = f'<link rel="alternate" type="{LINK_TYPE}" href="{href}">\n'
    path.write_bytes((html[: match.start()] + tag + html[match.start():]).encode("utf-8"))
    return True


# ---------------------------------------------------------------------------
# CLI


def render_result(result: Result, build: Path) -> str:
    lines = [f"Markdown for agents: {build}", ""]
    lines.append(
        f"  {len(result.written)} written, {len(result.unchanged)} unchanged, "
        f"{len(result.removed)} removed, {len(result.skipped)} skipped"
    )
    if result.linked:
        lines.append(f"  added <link rel=\"alternate\" type=\"text/markdown\"> to {len(result.linked)} page(s)")
    for path, reason in result.skipped:
        lines.append(f"  skipped {path}: {reason}")
    for path in result.removed:
        lines.append(f"  removed {path}: its page is gone or no longer exported")
    if result.llms_txt:
        lines.append(f"  llms.txt {result.llms_txt}")
    lines += [
        "",
        "Run this after every build, in the build script, so the Markdown never goes stale.",
        "Serving it for Accept: text/markdown needs one rule at the host: run with --setup.",
    ]
    return "\n".join(lines)


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Write Markdown for agents next to every built page")
    parser.add_argument("--no-link", action="store_true",
                        help="do not add <link rel=alternate type=text/markdown> to pages")
    parser.add_argument("--llms-txt", action="store_true",
                        help="also write llms.txt listing every exported page")
    parser.add_argument("--setup", action="store_true",
                        help="propose the host rule that serves the Markdown for Accept: text/markdown")
    parser.add_argument("--serve", help="host to generate the rule for, overriding `host` in siteseo.yaml")
    parser.add_argument("--apply", action="store_true", help="with --setup, write the proposed files")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.setup:
        import markdown_serve

        return markdown_serve.main(cfg, host=args.serve, apply=args.apply, as_json=args.json)

    try:
        result = export(cfg, link_tags=not args.no_link, llms_txt=args.llms_txt)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result.to_dict(), indent=2) if args.json else render_result(result, cfg.build_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

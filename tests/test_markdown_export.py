"""Markdown for agents, written at build time.

Sites are written into a temporary directory per test so the build step can
change files freely without touching the committed fixtures.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import agent_ready as AR
import config
import markdown_export as M

PAGE = """<!doctype html><html lang="en"><head><title>Demo page</title>
<meta name="description" content="A demo">
<link rel="canonical" href="https://x.example/demo/">
<script type="application/ld+json">{"@type":"Article","headline":"Demo"}</script></head>
<body><header><a href="/">Home</a><nav><a href="/a">Menu link</a></nav></header>
<article><header><h1>Demo <em>page</em></h1></header>
<p>Some <strong>bold</strong> text with a <a href="../other/">link</a> and <code>a_b</code>.<br>Next line.</p>
<ul><li>One</li><li>Two<ul><li>Nested <a href="https://e.com">ext</a></li></ul></li></ul>
<ol start="3"><li><p>Three</p></li><li>Four</li></ol>
<pre><code class="language-python">def f():
    return 1</code></pre>
<blockquote><p>Quoted</p><p>Twice</p></blockquote>
<table><tr><th>Song</th><th>Length</th></tr><tr><td>A | B</td><td>3:00</td></tr></table>
<img src="/img/a.png" alt="Cover"><audio src="/song.mp3" title="Listen"></audio>
<p>snake_case stays readable</p></article>
<footer>Copyright notice</footer><script>alert("never")</script></body></html>"""


def _page(tmp_path: Path, html: str, name: str = "page.html") -> M.Page:
    path = tmp_path / name
    path.write_text(html, encoding="utf-8")
    return M.extract(path, "https://x.example/demo/")


def _site(root: Path, files: dict[str, str]) -> config.Config:
    for relative, text in files.items():
        path = root / "dist" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return config.parse(
        {"site": "https://x.example", "stack": "plain-html", "build_dir": "dist"},
        root, where="test",
    )


def _doc(title: str, body: str, head: str = "") -> str:
    return (f"<!doctype html><html><head><title>{title}</title>{head}</head>"
            f"<body><main>{body}</main></body></html>")


# ------------------------------------------------------- conversion


def test_common_elements_convert(tmp_path):
    md = _page(tmp_path, PAGE).markdown
    for expected in (
        "# Demo *page*",
        "Some **bold** text with a [link](https://x.example/other/) and `a_b`.  \nNext line.",
        "- One\n- Two\n  - Nested [ext](https://e.com)",
        "3. Three\n4. Four",
        "```python\ndef f():\n    return 1\n```",
        "> Quoted\n>\n> Twice",
        "| Song | Length |\n| --- | --- |\n| A \\| B | 3:00 |",
        "![Cover](https://x.example/img/a.png)",
        "[Listen](https://x.example/song.mp3)",
        "snake_case stays readable",
    ):
        assert expected in md, expected


def test_site_chrome_and_scripts_are_left_out(tmp_path):
    md = _page(tmp_path, PAGE).markdown
    for absent in ("Menu link", "Copyright notice", "never", "Home"):
        assert absent not in md


def test_without_main_the_body_is_used_minus_chrome(tmp_path):
    html = ("<html><head><title>T</title></head><body><header>Site name</header>"
            "<h1>Body heading</h1><p>Body text</p><aside>Related</aside>"
            "<footer>Footer text</footer></body></html>")
    md = _page(tmp_path, html).markdown
    assert "# Body heading" in md and "Body text" in md
    assert "Site name" not in md and "Footer text" not in md and "Related" not in md


def test_title_becomes_the_heading_when_the_page_has_none(tmp_path):
    md = _page(tmp_path, _doc("Only a title", "<p>Text</p>")).markdown
    assert md.startswith("# Only a title\n\nText")


def test_frontmatter_marker_and_jsonld(tmp_path):
    text = M.render(_page(tmp_path, PAGE))
    head, _, rest = text.partition("\n---\n")
    assert head.splitlines() == [
        "---", 'title: "Demo page"', 'description: "A demo"',
        'url: "https://x.example/demo/"', 'lang: "en"', M.MARKER,
    ]
    assert rest.rstrip().endswith('```json\n{\n  "@type": "Article",\n  "headline": "Demo"\n}\n```')


# ------------------------------------------------------- the build step


def test_writes_a_markdown_file_next_to_each_page(tmp_path):
    cfg = _site(tmp_path, {
        "index.html": _doc("Home", "<h1>Home</h1>"),
        "about/index.html": _doc("About", "<h1>About</h1>"),
        "blog.html": _doc("Blog", "<h1>Blog</h1>"),
    })
    result = M.export(cfg)
    assert sorted(result.written) == ["about/index.md", "blog.md", "index.md"]
    about = (tmp_path / "dist" / "about" / "index.md").read_text(encoding="utf-8")
    assert 'url: "https://x.example/about/"' in about


def test_pages_an_agent_should_not_get_are_skipped(tmp_path):
    cfg = _site(tmp_path, {
        "index.html": _doc("Home", "<h1>Home</h1>"),
        "404.html": _doc("Not found", "<h1>Not found</h1>"),
        "private.html": _doc("Private", "<h1>P</h1>", '<meta name="robots" content="noindex">'),
        "moved.html": _doc("Moved", "", '<meta http-equiv="refresh" content="0; url=/">'),
    })
    result = M.export(cfg)
    assert result.written == ["index.md"]
    assert {path for path, _ in result.skipped} == {"404.html", "private.html", "moved.html"}


def test_a_hand_written_markdown_file_is_never_touched(tmp_path):
    cfg = _site(tmp_path, {"notes.html": _doc("Notes", "<h1>Notes</h1>"),
                           "notes.md": "# My own notes\n"})
    result = M.export(cfg)
    assert (tmp_path / "dist" / "notes.md").read_text(encoding="utf-8") == "# My own notes\n"
    assert result.skipped and "not written by siteseo" in result.skipped[0][1]


def test_only_stale_files_this_tool_wrote_are_removed(tmp_path):
    cfg = _site(tmp_path, {"a.html": _doc("A", "<h1>A</h1>"), "b.html": _doc("B", "<h1>B</h1>"),
                           "readme.md": "# Hand written\n"})
    M.export(cfg)
    (tmp_path / "dist" / "b.html").unlink()
    result = M.export(cfg)
    assert result.removed == ["b.md"]
    assert (tmp_path / "dist" / "readme.md").is_file()


def test_link_tag_is_added_once_and_a_second_run_changes_nothing(tmp_path):
    cfg = _site(tmp_path, {"index.html": _doc("Home", "<h1>Home</h1>"),
                           "about/index.html": _doc("About", "<h1>About</h1>")})
    first = M.export(cfg)
    assert sorted(first.linked) == ["about/index.html", "index.html"]
    html = (tmp_path / "dist" / "about" / "index.html").read_text(encoding="utf-8")
    assert '<link rel="alternate" type="text/markdown" href="/about/index.md">' in html

    snapshot = {p: p.read_bytes() for p in (tmp_path / "dist").rglob("*") if p.is_file()}
    second = M.export(cfg)
    assert second.written == [] and second.linked == [] and len(second.unchanged) == 2
    assert snapshot == {p: p.read_bytes() for p in (tmp_path / "dist").rglob("*") if p.is_file()}


def test_no_link_leaves_the_html_alone(tmp_path):
    cfg = _site(tmp_path, {"index.html": _doc("Home", "<h1>Home</h1>")})
    before = (tmp_path / "dist" / "index.html").read_bytes()
    M.export(cfg, link_tags=False)
    assert (tmp_path / "dist" / "index.html").read_bytes() == before


def test_export_needs_no_network(tmp_path, offline):
    cfg = _site(tmp_path, {"index.html": _doc("Home", "<h1>Home</h1>")})
    assert M.export(cfg).written == ["index.md"]


def test_the_gate_still_passes_after_export(tmp_path, repo_root):
    """Markdown files and link tags must not trip any search health check."""
    import gate

    site = tmp_path / "clean-site"
    shutil.copytree(repo_root / "tests" / "fixtures" / "clean-site", site)
    cfg = config.load(site / "siteseo.yaml")
    M.export(cfg)
    result = gate.run(cfg)
    assert result["passed"], [f["id"] for f in result["findings"] if f["severity"] == "error"]


def test_module_o_notices_exported_files_in_build_output(tmp_path):
    cfg = _site(tmp_path, {"index.html": _doc("Home", "<h1>Home</h1>"),
                           "robots.txt": "User-agent: *\nAllow: /\n"})
    M.export(cfg)
    check = next(c for c in AR.run(cfg)["checks"] if c["check"] == "markdown_negotiation")
    assert check["status"] == "unmeasured"
    assert "1 Markdown file" in check["summary"]


@pytest.mark.parametrize("missing", [None, "dist"])
def test_export_explains_a_missing_build(tmp_path, missing):
    cfg = config.parse({"site": "https://x.example", "build_dir": "dist"}, tmp_path, where="test")
    with pytest.raises(FileNotFoundError, match="Build the site first"):
        M.export(cfg)

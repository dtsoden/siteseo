"""Pages must be keyed by the URL the host serves, not by file name.

Cloudflare Pages, Netlify, Vercel and GitHub Pages all serve `about.html` at
`/about`. Real sites therefore write `/about` in their links, their canonicals
and their sitemap.

Keying pages by file name made siteseo treat `/about` and `/about.html` as two
different pages. On davidsoden.com that produced 35 false "canonical does not
point at itself" findings, 35 false orphan findings, 39 false "no inbound link"
findings, and a page count nearly double the real one. Every one of them was
wrong, and a tool that cries wolf on a correct site is worse than no tool.

These tests run against a fixture whose links, canonicals and sitemap all use
the extensionless form, which is what a real static site looks like.
"""

from __future__ import annotations

import pytest

import config as config_module
from source import BuildSource


@pytest.fixture(scope="module")
def clean_urls_site(repo_root):
    return config_module.load(repo_root / "tests" / "fixtures" / "clean-urls" / "siteseo.yaml")


@pytest.fixture(scope="module")
def src(clean_urls_site):
    source = BuildSource(clean_urls_site.build_path, clean_urls_site.origin)
    yield source
    source.close()


def test_files_are_keyed_by_served_url(src):
    served = {url for url, _ in src.walk_pages()}
    assert served == {
        "https://clean-urls.example.com/",
        "https://clean-urls.example.com/about",
        "https://clean-urls.example.com/reports/first",
    }
    assert not any(url.endswith(".html") for url in served)


@pytest.mark.parametrize(
    "spelling",
    [
        "https://clean-urls.example.com/about",
        "https://clean-urls.example.com/about.html",
        "https://clean-urls.example.com/about/",
    ],
)
def test_all_spellings_of_one_page_share_a_key(src, spelling):
    assert src.canonical_key(spelling) == src.canonical_key(
        "https://clean-urls.example.com/about"
    )


def test_distinct_pages_do_not_share_a_key(src):
    assert src.canonical_key("/about") != src.canonical_key("/reports/first")


def test_extensionless_url_still_fetches_the_file(src):
    response = src.fetch("https://clean-urls.example.com/about")
    assert response.status == 200
    assert b"<h1>About</h1>" in response.body


def test_no_false_canonical_orphan_or_inbound_findings(clean_urls_site):
    """The regression itself. Every one of these was fired wrongly before."""
    import gate

    result = gate.run(clean_urls_site)
    fired = {f["id"] for f in result["findings"]}

    for check_id in (
        "canonical.not_self_referencing",
        "structure.orphan_url",
        "links.no_inbound",
    ):
        assert check_id not in fired, (
            f"{check_id} fired on a correct extensionless-URL site. "
            "Pages are being keyed by file name again."
        )


def test_page_count_is_not_inflated(clean_urls_site):
    """Counting each page once under each spelling nearly doubled the total."""
    import crawl

    result = crawl.run(clean_urls_site, live=False)
    assert result["stats"]["pages_crawled"] == 3
    assert result["stats"]["pages_200"] == 3


def test_internal_links_resolve_so_depth_is_real(clean_urls_site):
    """Unresolved links made every page look unreachable from the homepage."""
    import crawl

    result = crawl.run(clean_urls_site, live=False)
    assert result["stats"]["max_depth"] <= 2, (
        "pages are unreachable from the homepage, so links are not resolving"
    )


def test_audit_writes_a_readable_report_and_no_empty_folders(clean_urls_site, tmp_path, monkeypatch):
    """An audit must leave a report a person can open, and nothing else.

    Creating history/, reports/ and imports/ up front left two empty folders in
    the repo after every audit, which reads as something having failed. A
    directory should appear because a file went into it.
    """
    import shutil

    import audit
    import config as config_module
    import history
    import report as report_module

    # Work on a copy so the fixture is not written into.
    site_dir = tmp_path / "site"
    shutil.copytree(clean_urls_site.root, site_dir)
    cfg = config_module.load(site_dir / "siteseo.yaml")

    result = audit.run(cfg, live=False, skip_perf=True)
    history.write(cfg, "audit", result)
    text = report_module.render(result, None)
    stamp = str(result.get("recorded_at") or "")[:10]
    (cfg.ensure_dir(cfg.reports_dir) / f"{stamp}-audit.md").write_text(text, encoding="utf-8")

    assert stamp, "the snapshot must carry a timestamp the report can be named with"
    assert cfg.history_dir.is_dir()
    assert cfg.reports_dir.is_dir()
    assert not cfg.imports_dir.exists(), (
        "imports/ was created without anything being written to it"
    )

    reports = list(cfg.reports_dir.glob("*.md"))
    assert len(reports) == 1
    assert reports[0].name.startswith(stamp), "report should be named by date, not 'report'"

    body = reports[0].read_text(encoding="utf-8")
    assert body.startswith("# siteseo report:")
    assert "Search health" in body and "AI access" in body

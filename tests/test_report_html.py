"""The styled report: plain-English titles, grouped findings, the site's logo."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import brand
import findings as F
import report_html

LOGO = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'


def test_every_check_has_a_plain_title():
    assert all(check.title.strip() for check in F.catalog().values())


def _snapshot():
    found = [
        F.make("http.status_4xx", "https://acme.example/a", "linked from /, returned 404"),
        F.make("ai.blocked_against_policy", "https://acme.example/", "GPTBot blocked", group="GPTBot"),
        F.make("ai.blocked_against_policy", "https://acme.example/", "ClaudeBot blocked", group="ClaudeBot"),
    ]
    return {
        "site": "https://acme.example",
        "recorded_at": "2026-10-15T00:00:00+00:00",
        "findings": [f.to_dict() for f in found],
        "scores": {"search_health": {"value": 80.0}, "ai_access": {"value": 60.0}},
        "modules": ["A", "E"],
    }


def test_report_uses_titles_and_groups_repeats():
    page = report_html.render(_snapshot())
    assert "Some links on your site lead to missing pages" in page
    # Two crawlers raising the same check are one item, not two.
    assert page.count("AI assistants you allow are being turned away") == 1


def test_logo_is_found_in_the_homepage_header(tmp_path: Path):
    build = tmp_path / "dist"
    (build / "brand").mkdir(parents=True)
    (build / "brand" / "mark.svg").write_bytes(LOGO)
    (build / "index.html").write_text(
        '<html><body><header><img src="/brand/mark.svg" alt="Acme"></header></body></html>',
        encoding="utf-8",
    )
    cfg = SimpleNamespace(site="https://acme.example", root=tmp_path, report_logo=None,
                          build_path=build, origin="https://acme.example")
    logo = brand.find(cfg)
    assert logo is not None and logo.mime == "image/svg+xml"
    assert logo.found_by == "a logo image on the homepage"
    assert logo.data_uri() in report_html.render(_snapshot(), logo=logo)


def test_report_logo_setting_wins(tmp_path: Path):
    (tmp_path / "logo.svg").write_bytes(LOGO)
    cfg = SimpleNamespace(site="https://acme.example", root=tmp_path, report_logo="logo.svg")
    logo = brand.find(cfg)
    assert logo is not None and logo.found_by == "report_logo in siteseo.yaml"
    assert logo.markdown_target(tmp_path / ".siteseo" / "reports") == "../../logo.svg"

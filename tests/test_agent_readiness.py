"""Module O: agent readiness.

The fixture sites are written into a temporary directory by each test rather
than committed. A skills index pins a SHA-256 digest of each SKILL.md, and a
committed file can pick up different line endings on a Windows checkout, which
would make the digest test pass or fail depending on the machine.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

import agent_ready as AR
import config
import findings as F
import fix
import source

HOME = (
    "<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Agent site</title>"
    "</head><body><h1>Agent site</h1></body></html>"
)
SITEMAP = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    "<url><loc>https://agent.example.com/</loc></url></urlset>"
)
SKILL = "# Hello skill\n\nSays hello.\n"


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _site(root: Path, files: dict[str, str], *, profile: str = "content",
          training: str = "allow", robots: str | None = None) -> config.Config:
    files = {"index.html": HOME, "sitemap.xml": SITEMAP, **files}
    if robots is not None:
        files["robots.txt"] = robots
    for relative, text in files.items():
        path = root / "dist" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    raw = {
        "site": "https://agent.example.com",
        "stack": "plain-html",
        "build_dir": "dist",
        "ai_policy": {"search_and_user_fetch": "allow", "training": training},
        "agent_readiness": {"profile": profile},
    }
    return config.parse(raw, root, where="test")


AGENT_ROBOTS = (
    "User-agent: *\n"
    "Content-Signal: ai-train=yes, search=yes, ai-input=maybe\n"
    "Allow: /\n\n"
    "User-agent: anthropic-ai\n"
    "Disallow: /\n\n"
    "Sitemap: https://agent.example.com/sitemap.xml\n"
)


def _agent_files() -> dict[str, str]:
    index = {
        "$schema": AR.SKILLS_SCHEMA,
        "skills": [
            {"name": "hello", "type": "skill-md", "description": "Says hello.",
             "url": "/.well-known/agent-skills/hello/SKILL.md", "digest": _sha(SKILL)},
            {"name": "other", "type": "skill-md", "description": "Digest is stale.",
             "url": "/.well-known/agent-skills/other/SKILL.md", "digest": "sha256:" + "0" * 64},
        ],
    }
    return {
        "index.html": HOME.replace(
            "</body>", "<script>navigator.modelContext.registerTool({name:'search'})</script></body>"
        ),
        "_headers": '/\n  Link: </.well-known/api-catalog>; rel="api-catalog"\n',
        ".well-known/api-catalog": json.dumps({"linkset": [{
            "anchor": "https://agent.example.com/api",
            "service-desc": [{"href": "https://agent.example.com/openapi.json"}],
        }]}),
        ".well-known/agent-skills/index.json": json.dumps(index),
        ".well-known/agent-skills/hello/SKILL.md": SKILL,
        ".well-known/agent-skills/other/SKILL.md": "# Other\n",
        ".well-known/mcp/server-card.json": json.dumps({"serverInfo": {"name": "demo", "version": "1.0.0"}}),
        ".well-known/agent-card.json": json.dumps({
            "name": "Demo", "url": "https://agent.example.com/a2a",
            "preferredTransport": "JSONRPC", "skills": [],
        }),
        "auth.md": "# Demo agent registration\n\nPOST to register_uri.\n",
        ".well-known/oauth-protected-resource": json.dumps({"resource": "https://agent.example.com/api"}),
        ".well-known/http-message-signatures-directory": json.dumps({"keys": []}),
        ".well-known/ai-catalog.json": json.dumps({"entries": [{
            "identifier": "urn:air:example:mcp:demo",
            "type": "application/mcp-server-card+json",
            "url": "/.well-known/mcp/server-card.json",
        }]}),
    }


@pytest.fixture
def agent_site(tmp_path):
    return _site(tmp_path, _agent_files(), profile="api", training="block", robots=AGENT_ROBOTS)


def _ids(result: dict) -> set[str]:
    return {finding["id"] for finding in result["findings"]}


def _status(result: dict) -> dict[str, str]:
    return {check["check"]: check["status"] for check in result["checks"]}


# ------------------------------------------------------- catalog and reference


def test_module_o_never_scores_and_never_blocks_a_deploy():
    checks = [c for c in F.catalog().values() if c.module == "O"]
    assert checks, "module O declares no checks"
    for check in checks:
        assert check.score == "none", f"{check.id} would move a score"
        assert check.severity != "error", f"{check.id} would block the gate"


def test_every_scanner_check_maps_to_a_check_the_run_records(tmp_path):
    cfg = _site(tmp_path, _agent_files(), profile="commerce", robots=AGENT_ROBOTS)
    recorded = set(_status(AR.run(cfg)))
    for standard in AR.reference()["standards"]:
        assert standard["check"] in recorded, standard["check"]
        assert standard["spec"].startswith("https://"), standard["check"]


def test_scanner_skill_pins_are_well_formed():
    pins = AR.reference()["scanner"]["skills"]
    assert len(pins) >= 20
    for name, digest in pins.items():
        assert re.fullmatch(r"[a-z0-9-]+", name)
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest), name


# ------------------------------------------------------- the ladder


def _state(statuses: dict[str, str]) -> AR.Run:
    cfg = config.parse({"site": "https://x.example"}, Path("."), where="test")
    state = AR.Run(cfg=cfg, probe=None)
    for name, status in statuses.items():
        state.record(name, status, "")
    return state


BOT_AWARE = {"robots_txt": "pass", "sitemap": "pass", "link_headers": "fail",
             "ai_rules": "pass", "content_signals": "pass"}


def test_two_of_three_basics_reach_level_one():
    level, ceiling = AR.compute_level(_state({**BOT_AWARE, "content_signals": "fail"}))
    assert (level, ceiling) == (1, None)


def test_an_unmeasured_check_is_a_ceiling_not_a_pass():
    """Cloudflare's scanner counts an excluded check as satisfied. siteseo does not."""
    level, ceiling = AR.compute_level(_state({**BOT_AWARE, "markdown_negotiation": "unmeasured"}))
    assert level == 2
    assert ceiling and "unmeasured" in ceiling


def test_level_zero_with_a_ceiling_when_the_third_basic_is_unmeasured():
    level, ceiling = AR.compute_level(
        _state({"robots_txt": "pass", "sitemap": "fail", "link_headers": "unmeasured"})
    )
    assert level == 0 and ceiling


def test_one_integration_document_reaches_level_four():
    state = _state({**BOT_AWARE, "markdown_negotiation": "pass", "agent_skills": "pass",
                    "mcp_card": "fail", "a2a_card": "fail", "api_catalog": "fail",
                    "web_bot_auth": "neutral", "oauth_discovery": "fail",
                    "protected_resource": "fail", "auth_md": "fail"})
    assert AR.compute_level(state) == (4, None)


def test_level_five_needs_two_of_three_groups():
    base = {**BOT_AWARE, "markdown_negotiation": "pass", "agent_skills": "pass",
            "mcp_card": "fail", "a2a_card": "fail", "api_catalog": "fail"}
    state = _state({**base, "web_bot_auth": "pass", "auth_md": "pass",
                    "oauth_discovery": "fail", "protected_resource": "fail"})
    assert AR.compute_level(state) == (5, None)


def test_content_profile_reports_level_five_as_undetermined():
    state = _state({**BOT_AWARE, "markdown_negotiation": "pass", "mcp_card": "pass",
                    "a2a_card": "pass", "agent_skills": "pass", "api_catalog": "pass",
                    "web_bot_auth": "neutral", "oauth_discovery": "skipped",
                    "protected_resource": "skipped", "auth_md": "skipped"})
    level, ceiling = AR.compute_level(state)
    assert level == 4 and "skipped" in ceiling


# ------------------------------------------------------- a site with agent documents


def test_agent_site_level_and_ceiling(agent_site):
    result = AR.run(agent_site)
    status = _status(result)
    assert status["link_headers"] == "pass", "the _headers file should count in build output"
    assert status["markdown_negotiation"] == "unmeasured"
    assert result["level"] == 2
    assert "Markdown" in (result["ceiling"] or "")
    assert result["next_level"]["level"] == 3


def test_agent_site_findings(agent_site):
    ids = _ids(AR.run(agent_site))
    expected = {
        "agent.content_signals_invalid",
        "agent.content_signals_contradict_policy",
        "agent.ai_rules_obsolete_token",
        "agent.skills_digest_mismatch",
        "agent.mcp_card_legacy_shape",
        "agent.a2a_card_legacy_shape",
        "agent.a2a_card_invalid",
        "agent.auth_md_invalid",
        "agent.auth_md_stale_fields",
        "agent.protected_resource_invalid",
        "agent.web_bot_auth_invalid",
        "agent.oauth_discovery_missing",
        "agent.webmcp_legacy_api",
        "agent.ard_legacy_location",
    }
    assert expected <= ids, f"did not fire: {sorted(expected - ids)}"
    for published in ("agent.api_catalog_missing", "agent.skills_index_missing",
                      "agent.link_headers_missing", "agent.mcp_card_missing"):
        assert published not in ids


def test_only_the_skill_with_the_wrong_digest_is_reported(agent_site):
    result = AR.run(agent_site)
    mismatch = next(f for f in result["findings"] if f["id"] == "agent.skills_digest_mismatch")
    assert "other" in mismatch["evidence"]
    assert "hello" not in mismatch["evidence"]
    assert _status(result)["agent_skills"] == "pass"


def test_a_content_site_is_not_told_to_build_an_api(clean_site):
    ids = {i for i in _ids(AR.run(clean_site)) if i.startswith("agent.")}
    assert ids == {"agent.content_signals_missing"}


def test_a_catch_all_html_page_is_absent_not_invalid(tmp_path):
    cfg = _site(tmp_path, {".well-known/api-catalog": HOME}, profile="api",
                robots="User-agent: *\nAllow: /\n")
    result = AR.run(cfg)
    assert _status(result)["api_catalog"] == "fail"
    assert "agent.api_catalog_invalid" not in _ids(result)
    assert "agent.api_catalog_missing" in _ids(result)


def test_the_gate_makes_no_request_for_module_o(clean_site, offline):
    """Build output needs no network, so module O runs under the offline flag."""
    result = AR.run(clean_site)
    assert result["source_kind"] == "build"


def test_audit_reports_the_level_beside_the_scores(clean_site):
    import audit

    result = audit.run(clean_site, live=False, skip_perf=True, skip_data=True)
    assert "O" in result["modules"]
    assert set(result["scores"]) == {"search_health", "ai_access"}
    assert result["agent_readiness"]["level"] >= 1


# ------------------------------------------------------- Content Signals


def test_signal_lines_carry_their_group_and_path():
    text = (
        "User-agent: GPTBot\nUser-agent: CCBot\nContent-Signal: /blog/ ai-train=no\n"
        "Disallow: /private\n\nUser-agent: *\nContent-signal: search=yes, ai-input=no\n"
    )
    first, second = AR.parse_signals(text)
    assert first.agents == ["GPTBot", "CCBot"]
    assert first.path == "/blog/" and first.pairs == {"ai-train": "no"}
    assert second.agents == ["*"] and second.pairs == {"search": "yes", "ai-input": "no"}


def test_cloudflare_managed_use_signal_is_not_invalid(tmp_path):
    robots = "User-Agent: *\nContent-signal: search=yes, ai-train=no, use=reference\nAllow: /\n"
    cfg = _site(tmp_path, {}, training="block", robots=robots)
    ids = _ids(AR.run(cfg))
    assert "agent.content_signals_invalid" not in ids
    assert "agent.content_signals_contradict_policy" not in ids


def test_signals_follow_ai_policy_unless_overridden(tmp_path):
    raw = {
        "site": "https://x.example",
        "ai_policy": {"search_and_user_fetch": "allow", "training": "allow"},
        # YAML reads a bare no as False, so both spellings have to work.
        "agent_readiness": {"content_signals": {"ai_train": False, "search": "yes"}},
    }
    cfg = config.parse(raw, tmp_path, where="test")
    assert cfg.content_signals() == {"search": True, "ai_input": True, "ai_train": False}
    assert AR.signal_line(cfg) == "Content-Signal: search=yes, ai-input=yes, ai-train=no"


@pytest.mark.parametrize("agent_readiness", [
    {"profile": "shop"},
    {"content_signals": {"ai_everything": "yes"}},
    {"content_signals": {"search": "maybe"}},
])
def test_bad_agent_readiness_config_names_the_field(tmp_path, agent_readiness):
    with pytest.raises(config.ConfigError, match="agent_readiness"):
        config.parse({"site": "https://x.example", "agent_readiness": agent_readiness},
                     tmp_path, where="test")


def test_generated_robots_agrees_with_its_own_policy(tmp_path):
    cfg = _site(tmp_path, {}, training="block", robots="")
    (tmp_path / "dist" / "robots.txt").write_text(fix.generate_robots(cfg), encoding="utf-8")
    ids = _ids(AR.run(cfg))
    assert not ids & {"agent.content_signals_missing", "agent.content_signals_invalid",
                      "agent.content_signals_contradict_policy"}


def test_signal_fix_keeps_every_other_rule():
    before = (
        "User-agent: *\nDisallow: /thank-you\nContent-Signal: ai-train=yes\n\n"
        "Sitemap: https://x.example/sitemap.xml\n"
    )
    after = fix.with_signal_line(before, "Content-Signal: search=yes, ai-input=yes, ai-train=no")
    assert after.splitlines()[:3] == [
        "User-agent: *", "Content-Signal: search=yes, ai-input=yes, ai-train=no",
        "Disallow: /thank-you",
    ]
    assert after.count("Content-Signal") == 1
    assert "Sitemap: https://x.example/sitemap.xml" in after


def test_signal_fix_adds_a_wildcard_group_when_there_is_none():
    after = fix.with_signal_line("User-agent: GPTBot\nDisallow: /\n", "Content-Signal: search=yes")
    assert after.startswith("User-agent: *\nContent-Signal: search=yes\nAllow: /\n")
    assert "User-agent: GPTBot" in after


def test_one_robots_proposal_per_plan(tmp_path):
    """Two fixers writing robots.txt from the same starting text would clobber each other."""
    cfg = _site(tmp_path, {}, robots="User-agent: *\nAllow: /\n")
    (tmp_path / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")

    def finding(check_id: str) -> dict:
        return {"id": check_id, "autofix": True, "fix": "", "urls": []}

    both = fix.build_plan(cfg, [finding("agent.content_signals_missing"),
                                finding("robots.no_sitemap_line")])
    assert len(both.proposals) == 1
    assert both.proposals[0].reason.startswith("regenerate")
    assert "Content-Signal:" in both.proposals[0].after

    alone = fix.build_plan(cfg, [finding("agent.content_signals_missing")])
    assert len(alone.proposals) == 1
    assert alone.proposals[0].reason.startswith("set the Content-Signal line")


# ------------------------------------------------------- header checks


class _FakeSource:
    def absolute(self, path: str) -> str:
        return "https://x.example" + path


class _FakeProbe:
    live = True
    src = _FakeSource()

    def __init__(self, response: source.Response):
        self.response = response

    def get(self, path: str, accept: str | None = None) -> source.Response:
        return self.response


@pytest.mark.parametrize("vary, warns", [("Origin", True), ("accept, Origin", False)])
def test_markdown_without_vary_accept_is_a_cache_hazard(vary, warns):
    cfg = config.parse({"site": "https://x.example"}, Path("."), where="test")
    response = source.Response(
        url="https://x.example/", status=200, body=b"# Hi",
        headers={"content-type": "text/markdown; charset=utf-8", "vary": vary},
    )
    state = AR.Run(cfg=cfg, probe=_FakeProbe(response))
    AR.check_markdown(state)
    assert state.passed("markdown_negotiation")
    assert any(f.id == "agent.markdown_missing_vary" for f in state.emitted) is warns


def test_link_header_relations_are_parsed():
    links = AR.parse_link_header(
        '</.well-known/api-catalog>; rel="api-catalog", </docs>; rel="service-doc describedby"'
    )
    assert links == [("/.well-known/api-catalog", {"api-catalog"}),
                     ("/docs", {"service-doc", "describedby"})]


# ------------------------------------------------------- Cloudflare comparison


def test_comparison_refuses_to_run_offline(clean_site, offline):
    with pytest.raises(source.OfflineRefused):
        AR.compare_cloudflare(clean_site, {"checks": [], "level": 0})


def test_only_definite_answers_can_disagree():
    assert AR._statuses_agree("pass", "pass") is True
    assert AR._statuses_agree("fail", "pass") is False
    assert AR._statuses_agree("unmeasured", "pass") is None
    assert AR._statuses_agree("pass", "neutral") is None


# ------------------------------------------------------- staying current


def _published(pins: dict[str, str]) -> dict:
    return {"skills": [{"name": name, "digest": digest} for name, digest in pins.items()]}


def test_sync_reports_scanner_skills_added_removed_and_changed(repo_root):
    import sync_upstream

    pins = dict(AR.reference()["scanner"]["skills"])
    pins.pop("ard")
    pins["content-signals"] = "sha256:" + "2" * 64
    pins["new-check"] = "sha256:" + "1" * 64

    report = sync_upstream.Report()
    sync_upstream.check_agent_scanner(repo_root, report, fetch=lambda url: _published(pins))
    found = {(d.kind, d.detail.split()[1] if d.kind != "added" else d.detail.split()[2])
             for d in report.code_drift}
    assert found == {("added", "new-check:"), ("removed", "ard"), ("content", "content-signals")}


def test_sync_is_quiet_when_nothing_moved(repo_root):
    import sync_upstream

    report = sync_upstream.Report()
    pins = AR.reference()["scanner"]["skills"]
    sync_upstream.check_agent_scanner(repo_root, report, fetch=lambda url: _published(pins))
    assert report.code_drift == [] and report.errors == []


def test_updating_pins_rewrites_only_the_digest_lines(tmp_path, repo_root):
    import sync_upstream

    original = repo_root / "skills" / "siteseo" / "reference" / "agent-readiness.yaml"
    target = tmp_path / "skills" / "siteseo" / "reference" / "agent-readiness.yaml"
    target.parent.mkdir(parents=True)
    target.write_bytes(original.read_bytes())

    pins = dict(AR.reference()["scanner"]["skills"])
    pins["acp"] = "sha256:" + "3" * 64
    assert sync_upstream.update_scanner_pins(tmp_path, fetch=lambda url: _published(pins)) is True

    before = original.read_text(encoding="utf-8").splitlines()
    after = target.read_text(encoding="utf-8").splitlines()
    changed = [(a, b) for a, b in zip(before, after) if a != b]
    assert len(before) == len(after)
    assert changed == [(f"    acp: {AR.reference()['scanner']['skills']['acp']}",
                        f"    acp: sha256:{'3' * 64}")]

"""The acceptance criteria from the design spec, as executable tests.

Each test here corresponds to a line in the spec's acceptance section. If one
fails, siteseo does not meet its own stated bar.
"""

from __future__ import annotations

import json
import re
import subprocess

import time
from pathlib import Path

import pytest

import findings as F


# ------------------------------------------------------- the check catalog


def test_every_check_has_evidence_fields_and_a_source():
    """Every finding carries evidence and a source URL."""
    for check in F.catalog().values():
        assert check.source.startswith(("http://", "https://", "RFC ")), check.id
        assert check.rule.strip(), check.id
        assert check.fix.strip(), check.id


def test_check_ids_are_unique_and_namespaced():
    ids = list(F.catalog())
    assert len(ids) == len(set(ids))
    for check_id in ids:
        assert re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", check_id), check_id


def test_a_finding_cannot_be_made_without_evidence():
    with pytest.raises(ValueError):
        F.make("title.missing", "https://example.com/", "   ")


def test_a_finding_cannot_use_an_id_outside_the_catalog():
    with pytest.raises(F.UnknownCheck):
        F.make("not.a.real.check", "https://example.com/", "evidence")


def test_findings_merge_by_id_severity_and_group():
    """One template fix clearing many URLs is one item, not many."""
    a = F.make("title.missing", "https://x/1", "no title")
    b = F.make("title.missing", "https://x/2", "no title")
    merged = F.merge([a, b])
    assert len(merged) == 1
    assert set(merged[0].urls) == {"https://x/1", "https://x/2"}
    assert merged[0].detail["url_count"] == 2


def test_different_groups_do_not_merge():
    """Two blocked crawlers are two fixes, so they stay two findings."""
    a = F.make("ai.blocked_against_policy", "https://x/", "GPTBot blocked", group="GPTBot")
    b = F.make("ai.blocked_against_policy", "https://x/", "ClaudeBot blocked", group="ClaudeBot")
    assert len(F.merge([a, b])) == 2


# ------------------------------------------------------- the fixtures


def test_clean_fixture_produces_zero_errors(clean_site):
    """A correct site must not be reported as broken."""
    import gate

    result = gate.run(clean_site)
    errors = [f for f in result["findings"] if f["severity"] == "error"]
    assert errors == [], f"clean fixture reported errors: {[e['id'] for e in errors]}"
    assert result["passed"] is True


def test_broken_fixture_produces_errors(broken_site):
    import gate

    result = gate.run(broken_site)
    assert result["passed"] is False
    assert result["counts"]["error"] > 0


def test_broken_fixture_covers_every_id_it_claims_to_seed(broken_site, repo_root):
    """Each fixture page lists the check ids it seeds. Those must actually fire.

    Runs the full offline audit rather than the gate, so modules A, B, C, E and
    G are all covered. Some ids cannot fire offline at all: checking an outbound
    link needs a network request, and the gate makes none by design. Those are
    marked `not-seeded-offline` in the fixture and are not claimed here.
    """
    import audit

    claimed: set[str] = set()
    build = repo_root / "tests" / "fixtures" / "broken-site" / "dist"
    for path in list(build.rglob("*.html")) + [build / "robots.txt", build / "sitemap.xml"]:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for block in re.findall(r"seeds:(.*?)(?:-->|not-seeded-offline)", text, re.S):
            claimed.update(re.findall(r"[a-z_]+\.[a-z0-9_]+", block))

    assert claimed, "no fixture page declares which check ids it seeds"

    found = {
        f["id"] for f in audit.run(broken_site, live=False, skip_perf=True)["findings"]
    }
    missing = sorted(claimed - found)
    assert not missing, f"fixture claims to seed these but they did not fire: {missing}"


def test_a_second_run_produces_identical_findings(clean_site):
    """Determinism: an unchanged site must produce the same result twice."""
    import gate

    first = gate.run(clean_site)["findings"]
    second = gate.run(clean_site)["findings"]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# ------------------------------------------------------- the gate


def test_gate_exits_nonzero_on_errors(repo_root):
    result = _run_gate(repo_root / "tests" / "fixtures" / "broken-site")
    assert result.returncode == 1
    assert "FAIL" in result.stdout


def test_gate_exits_zero_when_clean(repo_root):
    result = _run_gate(repo_root / "tests" / "fixtures" / "clean-site")
    assert result.returncode == 0
    assert "PASS" in result.stdout


def test_gate_finishes_quickly(clean_site):
    """The spec's budget is five minutes for 500 pages. A tiny site must be instant."""
    import gate

    started = time.perf_counter()
    gate.run(clean_site)
    assert time.perf_counter() - started < 30


def _run_gate(site_dir: Path) -> subprocess.CompletedProcess:
    import runtime

    return subprocess.run(
        [str(runtime.env_python()), str(runtime.PLUGIN_ROOT / "scripts" / "gate.py")],
        cwd=site_dir,
        capture_output=True,
        text=True,
        env={
            **_clean_env(),
            "PYTHONPATH": str(runtime.PLUGIN_ROOT / "scripts"),
            "SITESEO_PLUGIN_ROOT": str(runtime.PLUGIN_ROOT),
        },
    )


def _clean_env() -> dict:
    import os

    return {k: v for k, v in os.environ.items() if k != "SITESEO_OFFLINE"}


# ------------------------------------------------------- secrets never leak


def test_no_secret_is_committed_anywhere_in_the_repo(repo_root):
    """No secret is ever written under the repo."""
    patterns = [
        re.compile(r"AIza[0-9A-Za-z_-]{35}"),           # Google API key
        re.compile(r"GOCSPX-[A-Za-z0-9_-]{20,}"),        # Google OAuth client secret
        re.compile(r"ya29\.[A-Za-z0-9_-]{20,}"),         # Google OAuth access token
        re.compile(r"[0-9]{10,}-[a-z0-9]{32}\.apps\.googleusercontent\.com"),
        re.compile(r"sk-[A-Za-z0-9]{32,}"),              # OpenAI style
        re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),        # Anthropic style
        re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
        re.compile(r'"private_key"\s*:\s*"-----BEGIN'),  # service account JSON
        re.compile(r'"client_secret"\s*:\s*"[^"]{10,}"'),
    ]
    skip_dirs = {".git", "exclude", "__pycache__", ".pytest_cache", "node_modules"}

    offenders = []
    for path in repo_root.rglob("*"):
        if not path.is_file() or any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix in {".png", ".jpg", ".gz", ".ico", ".woff", ".woff2"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in patterns:
            if pattern.search(text):
                offenders.append(f"{path.relative_to(repo_root)}: {pattern.pattern}")

    assert not offenders, f"possible secrets in the repo: {offenders}"


def test_secrets_module_never_returns_a_value_it_cannot_source(monkeypatch):
    import secrets as vault

    monkeypatch.delenv("SITESEO_PAGESPEED_API_KEY", raising=False)
    monkeypatch.setattr(vault, "vault_names", lambda: frozenset())
    assert vault.get("SITESEO_PAGESPEED_API_KEY") is None
    assert vault.available("SITESEO_PAGESPEED_API_KEY") is False
    assert "not set" in vault.describe("SITESEO_PAGESPEED_API_KEY")


def test_secrets_are_never_read_by_echoing_them_out(repo_root):
    """The vault must be asked to inject, never to print.

    A vault worth using scrubs stored values out of its child's output, so an
    earlier version of secrets.py that ran `aihsm run -- python -c print(value)`
    got back four asterisks. Injection happens in the launcher instead.
    """
    import ast

    source = (repo_root / "scripts" / "secrets.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Every string literal handed to a subprocess call, docstrings excluded.
    invoked: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = ast.unparse(node.func)
        if "subprocess" not in target and "Popen" not in target:
            continue
        for arg in node.args:
            for literal in ast.walk(arg):
                if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                    invoked.append(literal.value)

    assert invoked, "expected at least one subprocess call to inspect"
    assert set(invoked) <= {"aihsm", "list"}, (
        f"secrets.py runs aihsm with {invoked}. It may only list names; asking "
        "the vault to print a value gets four asterisks back."
    )
    assert "os.environ.get(name)" in source


def test_describe_never_prints_a_value(monkeypatch):
    import secrets as vault

    monkeypatch.setenv("SITESEO_PAGESPEED_API_KEY", "super-secret-value-12345")
    described = vault.describe("SITESEO_PAGESPEED_API_KEY")
    assert "super-secret-value-12345" not in described
    assert "available" in described


def test_redact_removes_known_values(monkeypatch):
    import secrets as vault

    monkeypatch.setenv("SITESEO_OPENAI_API_KEY", "abcdef1234567890")
    assert "abcdef1234567890" not in vault.redact("failed with key abcdef1234567890")


# ------------------------------------------------------- scoring


def test_the_two_scores_are_never_combined():
    import score

    result = score.both([], urls_checked=10, bots=[])
    assert set(result) == {"search_health", "ai_access"}
    assert "overall" not in result
    assert "total" not in result
    rendered = score.render(result)
    assert "never combined" in rendered


def test_blocked_crawlers_are_excluded_from_the_ai_denominator():
    """Blocking a training crawler on purpose is a choice, not a failure."""
    import score

    bots = [
        {"token": "GPTBot", "intended": "block", "robots_allowed": False,
         "fetch_tested": False, "effective_allowed": False},
        {"token": "OAI-SearchBot", "intended": "allow", "robots_allowed": True,
         "fetch_tested": True, "fetch_statuses": {"/": 200}, "effective_allowed": True},
    ]
    assert score.ai_access(bots).value == 100.0


def test_network_failure_does_not_count_as_blocked():
    import score

    bots = [{
        "token": "GPTBot", "intended": "allow", "robots_allowed": True,
        "fetch_tested": False, "fetch_statuses": {"/": 0, "/a": 0},
        "effective_allowed": True,
    }]
    assert score.ai_access(bots).value == 100.0


def test_a_refused_fetch_does_count_as_blocked():
    import score

    bots = [{
        "token": "GPTBot", "intended": "allow", "robots_allowed": True,
        "fetch_tested": True, "fetch_statuses": {"/": 403},
        "effective_allowed": False,
    }]
    assert score.ai_access(bots).value == 0.0


def test_a_url_broken_for_everyone_is_not_a_blocked_crawler():
    """One page that 403s for every visitor must not tank AI access.

    Found on a real site: /music/ was a directory with no index page, so nginx
    returned 403 to browsers and crawlers alike. Scoring counted it as every
    crawler being refused and reported AI access at 10.5 on a site that blocks
    nothing.
    """
    import ai_matrix

    result = ai_matrix.BotResult(
        bot=ai_matrix.Bot(token="GPTBot", operator="OpenAI", purpose="training",
                          docs="https://example.com", user_agent="GPTBot/1.0"),
        robots_allowed=True,
        robots_rule="no matching rule",
        intended="allow",
        fetch_statuses={"/": 200, "/music/": 403},
        fetch_tested=True,
        baseline={"/": 200, "/music/": 403},
    )
    assert result.blocked_for_bot_only == []
    assert result.effective_allowed is True

    # The same 403 where a browser gets 200 is a real block.
    result.baseline = {"/": 200, "/music/": 200}
    assert result.blocked_for_bot_only == ["/music/"]
    assert result.effective_allowed is False


def test_warnings_are_charged_per_type_not_per_url():
    import score

    many_urls = [{
        "id": "canonical.missing", "module": "A", "score": "search",
        "severity": "warning", "urls": [f"https://x/{i}" for i in range(40)],
    }]
    result = score.search_health(many_urls, urls_checked=40)
    assert result.components["warning_types"] == 1
    assert result.components["warning_deduction"] == 1.5


# ------------------------------------------------------- reference data


def test_every_bot_maps_to_a_policy_key():
    import ai_matrix

    for bot in ai_matrix.load_bots():
        assert bot.policy_key in {"training", "search_and_user_fetch"}
        assert bot.docs.startswith("https://")


def test_control_tokens_are_not_fetched():
    """Google-Extended and Applebot-Extended are robots controls, not crawlers."""
    import ai_matrix

    by_token = {bot.token: bot for bot in ai_matrix.load_bots()}
    for token in ("Google-Extended", "Applebot-Extended"):
        assert by_token[token].fetches is False, f"{token} must not be fetch-tested"


def test_reference_files_carry_a_last_verified_date(repo_root):
    reference = repo_root / "skills" / "siteseo" / "reference"
    for path in reference.iterdir():
        if path.suffix in {".yaml", ".yml", ".md"}:
            text = path.read_text(encoding="utf-8")
            assert re.search(r"last_verified:\s*\d{4}-\d{2}-\d{2}", text), path.name


def test_faq_and_howto_are_never_recommended(repo_root):
    """Google narrowed FAQ and dropped HowTo rich results in 2023."""
    import schema_check

    types, _ = schema_check.load_types()
    for name in ("FAQPage", "HowTo"):
        assert types[name]["rich_result"] is False


# ------------------------------------------------------- vendoring


def test_upstream_lock_pins_every_vendored_file(repo_root):
    import hashlib

    lock = json.loads((repo_root / "upstream.lock").read_text(encoding="utf-8"))
    assert lock["sources"], "upstream.lock declares no sources"

    for source in lock["sources"]:
        assert source["commit"], source["repo"]
        assert source["license"], source["repo"]
        for relative, pinned in source["files"].items():
            name = Path(relative).name if relative == "LICENSE" else relative
            path = repo_root / "vendor" / source["repo"].split("/")[-1] / name
            assert path.is_file(), f"missing vendored file {path}"
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            assert actual == pinned, f"{relative} does not match its pinned hash"


def test_every_vendored_source_has_a_licence_and_a_notice(repo_root):
    notices = (repo_root / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    lock = json.loads((repo_root / "upstream.lock").read_text(encoding="utf-8"))
    for source in lock["sources"]:
        assert source["repo"] in notices, f"{source['repo']} is not in THIRD_PARTY_NOTICES.md"
        licence = repo_root / "vendor" / source["repo"].split("/")[-1] / "LICENSE"
        assert licence.is_file(), f"no licence vendored for {source['repo']}"


# ------------------------------------------------------- packaging


def test_no_internal_asset_is_tracked_by_git(repo_root):
    """The exclude/ folder must never reach the public repository."""
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=repo_root, capture_output=True, text=True
    ).stdout.splitlines()
    leaked = [path for path in tracked if path.startswith("exclude/")]
    assert not leaked, f"internal files are tracked by git: {leaked}"


def test_nothing_references_an_absolute_machine_path(repo_root):
    """A hardcoded path breaks the moment the plugin lands on another machine."""
    offenders = []
    for directory in ("scripts", "skills", "agents"):
        for path in (repo_root / directory).rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".md", ".yaml", ""}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r"[A-Z]:\\\\?[Uu]sers|/Users/[a-z]|/home/[a-z]", text):
                offenders.append(f"{path.relative_to(repo_root)}: {match.group(0)}")
    assert not offenders, f"absolute machine paths found: {offenders}"


def test_plugin_manifest_matches_the_skill(repo_root):
    manifest = json.loads(
        (repo_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "siteseo"
    assert manifest["license"] == "MIT"

    marketplace = json.loads(
        (repo_root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    assert marketplace["plugins"][0]["name"] == manifest["name"]


def test_every_command_in_the_skill_has_a_script(repo_root):
    skill = (repo_root / "skills" / "siteseo" / "SKILL.md").read_text(encoding="utf-8")
    scripts = {p.stem for p in (repo_root / "scripts").glob("*.py")}
    # Commands that map to a script of the same or a stated name.
    expected = {
        "audit": "audit", "ai": "ai_matrix", "fix": "fix", "report": "report",
        "gate": "gate", "doctor": "doctor", "sync": "sync_upstream",
        "track": "ai_probe", "research": "dataforseo",
    }
    for command, script in expected.items():
        assert f"/siteseo {command}" in skill, f"{command} is not documented in SKILL.md"
        assert script in scripts, f"{script}.py is missing for /siteseo {command}"




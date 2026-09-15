"""The guided flow behind a bare `/siteseo`: status, init with values, full report."""

from __future__ import annotations

import ast
import json
import sys

import yaml

import config
import findings as F
import report
import status


def _repo(tmp_path, monkeypatch, *, ready: bool = True):
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(status.runtime, "is_ready", lambda: ready)
    return tmp_path


# ------------------------------------------------------- status


def test_status_runs_on_the_standard_library_alone(repo_root):
    """It has to answer before setup has built the environment."""
    tree = ast.parse((repo_root / "scripts" / "status.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    third_party = {name for name in imported - {"runtime"} if name not in sys.stdlib_module_names}
    assert not third_party, third_party


def test_setup_comes_first(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch, ready=False)
    assert status.state()["next_step"] == "setup"


def test_an_unconfigured_repo_asks_for_init_and_offers_what_it_detected(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    (root / "astro.config.mjs").write_text("", encoding="utf-8")
    (root / "netlify.toml").write_text("", encoding="utf-8")
    (root / "dist").mkdir()
    (root / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")

    result = status.state()
    assert result["next_step"] == "init"
    assert result["config"] is None
    assert result["detected"] == {"stack": "astro", "host": "netlify", "server": None,
                                  "build_dirs": ["dist"]}


def test_a_hand_written_site_behind_nginx_is_recognised(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    (root / "index.html").write_text("<html></html>", encoding="utf-8")
    (root / "nginx.conf").write_text("server {}", encoding="utf-8")
    (root / "Dockerfile").write_text("FROM nginx", encoding="utf-8")
    detected = status.state()["detected"]
    assert detected["build_dirs"] == ["."] and detected["server"] == "nginx"


def test_a_parent_folder_points_at_the_site_below_it(tmp_path, monkeypatch):
    """Running from a folder that holds the site should not configure the folder."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(status.runtime, "is_ready", lambda: True)
    site = tmp_path / "example-site"
    (site / ".git").mkdir(parents=True)
    (site / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "Album artwork").mkdir()

    result = status.state()
    assert result["next_step"] == "choose_site"
    assert result["nearby_sites"] == ["example-site"]


def test_an_old_report_without_agent_readiness_reads_plainly(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    (root / "siteseo.yaml").write_text(config.starter(site="https://x.example", build_dir="."),
                                       encoding="utf-8")
    history = root / ".siteseo" / "history"
    history.mkdir(parents=True)
    (history / "2026-09-11-120000-audit.json").write_text(
        json.dumps({"recorded_at": "2026-09-11T12:00:00+00:00",
                    "scores": {"search_health": {"value": 90.0}, "ai_access": {"value": 100.0}}}),
        encoding="utf-8")
    text = status.render(status.state())
    assert "agent readiness not in that report" in text and "None" not in text


def test_steps_advance_from_build_to_first_report_to_ready(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    (root / "siteseo.yaml").write_text(config.starter(site="https://x.example"), encoding="utf-8")
    assert status.state()["next_step"] == "build"

    (root / "dist").mkdir()
    assert status.state()["next_step"] == "first_report"

    history = root / ".siteseo" / "history"
    history.mkdir(parents=True)
    (history / "2026-09-15-120000-audit.json").write_text(json.dumps({
        "recorded_at": "2026-09-15T12:00:00+00:00",
        "scores": {"search_health": {"value": 91.5}, "ai_access": {"value": 100.0}},
        "agent_readiness": {"level": 1, "level_name": "Basic Web Presence"},
    }), encoding="utf-8")
    result = status.state()
    assert result["next_step"] == "ready"
    assert result["latest_audit"]["search_health"] == 91.5
    assert result["latest_audit"]["agent_level"] == 1
    assert result["config"]["site"] == "https://x.example"


def test_status_is_found_from_a_subdirectory(tmp_path, monkeypatch):
    root = _repo(tmp_path, monkeypatch)
    (root / "siteseo.yaml").write_text(config.starter(site="https://x.example"), encoding="utf-8")
    (root / "src" / "pages").mkdir(parents=True)
    monkeypatch.chdir(root / "src" / "pages")
    assert status.state()["config"]["path"] == str(root / "siteseo.yaml")


# ------------------------------------------------------- init with values


def test_starter_fills_answers_and_keeps_the_comments(tmp_path):
    text = config.starter(site="https://demo.example", build_dir="build", host="netlify",
                          stack="astro", profile="api", training="block", search="allow")
    cfg = config.parse(yaml.safe_load(text), tmp_path, where="test")
    assert cfg.site == "https://demo.example"
    assert cfg.build_dir == "build" and cfg.host == "netlify" and cfg.stack == "astro"
    assert cfg.agent_readiness.profile == "api"
    assert cfg.ai_policy.training == "block" and cfg.ai_policy.search_and_user_fetch == "allow"
    assert "# netlify, vercel, cloudflare-pages, github-pages, other" in text
    assert "npx serve build" in text


def test_init_writes_once_and_never_overwrites(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["config.py", "--init", "--site", "https://demo.example"])
    assert config.main() == 0
    assert "https://demo.example" in (tmp_path / "siteseo.yaml").read_text(encoding="utf-8")
    assert config.main() == 1
    assert "already exists" in capsys.readouterr().out


def test_init_refuses_a_value_that_would_not_load(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["config.py", "--init", "--site", "demo.example"])
    assert config.main() == 1
    assert not (tmp_path / "siteseo.yaml").exists()


# ------------------------------------------------------- the full report


def test_report_says_what_was_checked_and_what_was_not():
    snapshot = {
        "site": "https://x.example",
        "modules": ["A", "B", "D", "E", "O"],
        "skipped": ["module D (performance): no PageSpeed key"],
        "findings": [F.make("title.missing", "https://x.example/", "no title").to_dict()],
        "bots": [{
            "token": "GPTBot", "operator": "OpenAI", "purpose": "training", "intended": "allow",
            "robots_allowed": True, "fetch_tested": True, "fetch_statuses": {"/": 200},
            "matches_policy": True,
        }],
        "scores": {},
    }
    text = report.render(snapshot)
    assert "| A | Crawl and indexability | checked, nothing found |" in text
    assert "| B | On-page | 1 error |" in text
    assert "| D | Performance | not run: no PageSpeed key |" in text
    assert "| K | AI visibility | not part of the audit:" in text
    assert "| H | International | not run |" in text
    assert "| GPTBot | OpenAI | training | allow | allowed | 200 | yes |" in text


def test_audit_covers_international_and_local(clean_site):
    import audit

    result = audit.run(clean_site, live=False, skip_perf=True, skip_data=True)
    assert {"H", "I"} <= set(result["modules"])
    assert any(item.startswith("module H") for item in result["skipped"])

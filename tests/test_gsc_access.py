"""`gsc.py --whoami`: which account is configured, and what it can read.

The question this answers is the one nobody can answer months later: which
service account did I make, and was this site ever granted to it. No test here
touches the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import config
import gsc

KEY = {
    "type": "service_account",
    "project_id": "demo-project",
    "client_email": "seo@demo-project.iam.gserviceaccount.com",
    # Deliberately not key-shaped: the repo's own secret scan fails the build on
    # anything that looks like a real private key, including in a fixture.
    "private_key": "not-a-real-key, and whoami never reads this field",
}


class _Sites:
    def __init__(self, entries):
        self.entries = entries

    def list(self):
        return self

    def execute(self):
        return {"siteEntry": self.entries}


class _Service:
    def __init__(self, entries):
        self.entries = entries

    def sites(self):
        return _Sites(self.entries)


def _cfg(root: Path, site: str = "https://example.com") -> config.Config:
    return config.parse({"site": site}, root, where="test")


def _configure(monkeypatch, tmp_path: Path, entries) -> Path:
    key_path = tmp_path / "key.json"
    key_path.write_text(json.dumps(KEY), encoding="utf-8")
    monkeypatch.setattr(gsc.secrets, "get", lambda name: str(key_path))
    monkeypatch.setattr(gsc, "_service", lambda: (_Service(entries), None))
    return key_path


def test_an_unconfigured_machine_points_at_the_readme(monkeypatch, tmp_path):
    monkeypatch.setattr(gsc.secrets, "get", lambda name: None)
    result = gsc.whoami(_cfg(tmp_path))
    assert result["configured"] is False
    assert "Connecting Google" in result["reason"]
    assert "not configured" in gsc.render_whoami(result)


def test_it_names_the_account_and_the_property_for_this_site(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, [
        {"siteUrl": "sc-domain:example.com", "permissionLevel": "siteRestrictedUser"},
        {"siteUrl": "https://other.example/", "permissionLevel": "siteFullUser"},
    ])
    result = gsc.whoami(_cfg(tmp_path))
    assert result["service_account"] == KEY["client_email"]
    assert result["project"] == "demo-project"
    assert result["property_for_this_site"] == "sc-domain:example.com"
    assert result["reason"] is None
    assert len(result["properties"]) == 2

    text = gsc.render_whoami(result)
    assert KEY["client_email"] in text
    assert "(readable)" in text
    assert "siteRestrictedUser" in text


def test_a_site_nobody_granted_says_exactly_what_to_do(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, [
        {"siteUrl": "sc-domain:other.example", "permissionLevel": "siteFullUser"},
    ])
    result = gsc.whoami(_cfg(tmp_path))
    assert result["property_for_this_site"] is None
    assert KEY["client_email"] in result["reason"]
    assert "Restricted" in result["reason"]
    assert "Users and permissions" in result["reason"]


def test_the_url_prefix_form_counts_too(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, [
        {"siteUrl": "https://example.com/", "permissionLevel": "siteFullUser"},
    ])
    assert gsc.whoami(_cfg(tmp_path))["property_for_this_site"] == "https://example.com/"


def test_the_key_itself_is_never_shown(monkeypatch, tmp_path):
    key_path = _configure(monkeypatch, tmp_path, [])
    text = gsc.render_whoami(gsc.whoami(_cfg(tmp_path)))
    assert str(key_path) not in text
    assert "PRIVATE KEY" not in text


def test_an_unreadable_key_path_is_reported_without_the_path(monkeypatch, tmp_path):
    missing = tmp_path / "gone.json"
    monkeypatch.setattr(gsc.secrets, "get", lambda name: str(missing))
    result = gsc.whoami(_cfg(tmp_path))
    assert result["service_account"] is None
    assert "could not read the key file" in result["reason"]

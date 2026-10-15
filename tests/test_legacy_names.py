"""Sites, machines and vaults set up before the rename from siteseo keep working."""

from __future__ import annotations

import config
import markdown_export
import naming
import secrets as vault
import status


def test_legacy_config_file_is_found(tmp_path):
    (tmp_path / "siteseo.yaml").write_text(config.starter(site="https://x.example"), encoding="utf-8")
    assert config.find_config(tmp_path) == tmp_path / "siteseo.yaml"
    assert status.state(tmp_path)["config"]["path"] == str(tmp_path / "siteseo.yaml")


def test_new_config_file_wins_over_legacy(tmp_path):
    for name in ("siteseo.yaml", "siteseoai.yaml"):
        (tmp_path / name).write_text(config.starter(site="https://x.example"), encoding="utf-8")
    assert config.find_config(tmp_path) == tmp_path / "siteseoai.yaml"


def test_legacy_state_folder_is_kept_until_moved(tmp_path):
    (tmp_path / "siteseoai.yaml").write_text(config.starter(site="https://x.example"), encoding="utf-8")
    assert config.load(tmp_path / "siteseoai.yaml").state_dir == tmp_path / ".siteseoai"

    (tmp_path / ".siteseo" / "history").mkdir(parents=True)
    assert config.load(tmp_path / "siteseoai.yaml").state_dir == tmp_path / ".siteseo"

    (tmp_path / ".siteseoai").mkdir()
    assert config.load(tmp_path / "siteseoai.yaml").state_dir == tmp_path / ".siteseoai"


def test_legacy_environment_names_are_read(monkeypatch):
    monkeypatch.delenv("SITESEOAI_PAGESPEED_API_KEY", raising=False)
    monkeypatch.setenv("SITESEO_PAGESPEED_API_KEY", "old-name-value-123")
    assert vault.get("SITESEOAI_PAGESPEED_API_KEY") == "old-name-value-123"

    monkeypatch.setenv("SITESEOAI_PAGESPEED_API_KEY", "new-name-value-456")
    assert vault.get("SITESEOAI_PAGESPEED_API_KEY") == "new-name-value-456"


def test_adopt_legacy_env_fills_only_missing_names():
    env = {"SITESEO_OFFLINE": "1", "SITESEO_BING_API_KEY": "old", "SITESEOAI_BING_API_KEY": "new"}
    adopted = naming.adopt_legacy_env(env)
    assert adopted == ["SITESEOAI_OFFLINE"]
    assert env["SITESEOAI_OFFLINE"] == "1"
    assert env["SITESEOAI_BING_API_KEY"] == "new"


def test_vault_secret_under_old_name_is_injected_under_new_name(monkeypatch):
    monkeypatch.setattr(vault, "vault_names", lambda: frozenset({"SITESEO_BING_API_KEY"}))
    assert ("SITESEOAI_BING_API_KEY", "SITESEO_BING_API_KEY") in vault.injections()


def test_markdown_written_before_the_rename_counts_as_ours(tmp_path):
    page = tmp_path / "about.md"
    page.write_text("---\ntitle: About\ngenerator: siteseo\n---\n\nBody\n", encoding="utf-8")
    assert markdown_export.generated_by_us(page)

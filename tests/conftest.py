"""Shared fixtures. Tests import siteseo modules directly from scripts/."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"

sys.path.insert(0, str(SCRIPTS))
os.environ.setdefault("SITESEO_PLUGIN_ROOT", str(REPO_ROOT))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def clean_site():
    import config

    return config.load(REPO_ROOT / "tests" / "fixtures" / "clean-site" / "siteseo.yaml")


@pytest.fixture(scope="session")
def broken_site():
    import config

    return config.load(REPO_ROOT / "tests" / "fixtures" / "broken-site" / "siteseo.yaml")


@pytest.fixture
def offline(monkeypatch):
    """Force the offline guarantee on, the way the gate does."""
    monkeypatch.setenv("SITESEO_OFFLINE", "1")
    yield

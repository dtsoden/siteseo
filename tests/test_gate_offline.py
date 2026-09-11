"""The gate makes no model call and no paid API call.

The spec asks for this to be proven, not promised. The proof is structural: the
gate sets SITESEO_OFFLINE, and LiveSource refuses to be constructed while that is
set. These tests assert the refusal actually fires and that the gate still
produces a full result with the network unavailable.
"""

from __future__ import annotations

import os

import pytest

import gate
import source


def test_live_source_refuses_while_offline(offline):
    with pytest.raises(source.OfflineRefused):
        source.LiveSource("https://example.com")


def test_build_source_still_works_while_offline(offline, clean_site):
    src = source.BuildSource(clean_site.build_path, clean_site.origin)
    response = src.fetch("/")
    assert response.status == 200
    assert b"<h1>" in response.body


def test_build_source_refuses_to_invent_a_result_for_an_external_url(offline, clean_site):
    """An external URL has no file in the build and must not be fetched."""
    src = source.BuildSource(clean_site.build_path, clean_site.origin)
    response = src.fetch("https://some-other-site.example/page")
    assert response.status == 0
    assert "external URL" in (response.error or "")


def test_gate_completes_with_the_network_refused(clean_site):
    """The gate's own run must never need a connection."""
    result = gate.run(clean_site)
    assert result["passed"] is True
    assert result["stats"]["pages_crawled"] > 0
    assert result["modules"] == ["A", "B", "C", "E"]


def test_gate_restores_the_environment_it_found(clean_site):
    """Leaving the flag set would make every later call silently offline."""
    assert "SITESEO_OFFLINE" not in os.environ
    gate.run(clean_site)
    assert "SITESEO_OFFLINE" not in os.environ


def test_gate_restores_a_pre_existing_value(clean_site, monkeypatch):
    monkeypatch.setenv("SITESEO_OFFLINE", "already-set")
    gate.run(clean_site)
    assert os.environ["SITESEO_OFFLINE"] == "already-set"


def test_gate_excludes_the_module_that_costs_money():
    """Module D needs a PageSpeed key and a round trip, so it is never in the gate."""
    assert "D" not in gate.MODULES


def test_no_provider_endpoint_is_reachable_from_the_gate_path():
    """Nothing the gate imports may reference a paid or model endpoint."""
    import ai_matrix
    import crawl
    import schema_check

    banned = (
        "api.anthropic.com", "api.openai.com", "api.perplexity.ai",
        "api.dataforseo.com", "pagespeedonline", "chromeuxreport",
    )
    for module in (gate, crawl, schema_check, ai_matrix):
        path = module.__file__
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        for endpoint in banned:
            assert endpoint not in text, f"{module.__name__} references {endpoint}"

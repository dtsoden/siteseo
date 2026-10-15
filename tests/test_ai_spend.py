"""Module K spends money, so it asks first and stops at the cap.

Every provider call is metered on the user's own account. These tests prove that
no call is made without --confirm, none is made past budget.monthly_usd, a run
that overshoots its estimate stops at the cap, and the next estimate comes from
the median of what earlier runs actually cost. No test here touches the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ai_probe
import config
import dataforseo


def _cfg(root: Path, budget: float) -> config.Config:
    return config.parse(
        {"site": "https://example.com", "prompts": ["how do I test this", "second question"],
         "budget": {"monthly_usd": budget}},
        root,
        where="test",
    )


@pytest.fixture
def anthropic_only(monkeypatch):
    monkeypatch.setattr(
        ai_probe.secrets, "get",
        lambda name: "k" if name == "SITESEOAI_ANTHROPIC_API_KEY" else None,
    )
    monkeypatch.setattr(ai_probe, "build_prompts", lambda cfg: (list(cfg.prompts), []))
    calls: list[str] = []

    def ask(prompt, key, model):
        calls.append(prompt)
        answer = ai_probe.Answer("anthropic", model, prompt, 0, text="https://example.com")
        answer.cost_usd = 0.05
        return answer

    monkeypatch.setitem(ai_probe.ASK, "anthropic", ask)
    return calls


def test_nothing_is_called_without_confirm(tmp_path, anthropic_only):
    result = ai_probe.run(_cfg(tmp_path, 10), runs=3)
    assert anthropic_only == []
    assert result["available"] is False and result["needs_confirmation"] is True
    assert "--confirm" in result["reason"]
    # Two prompts, three runs, one provider, at the first-run placeholder.
    assert result["estimate_usd"] == pytest.approx(6 * ai_probe.FIRST_RUN_ESTIMATE["anthropic"])


def test_a_zero_budget_refuses_even_with_confirm(tmp_path, anthropic_only):
    result = ai_probe.run(_cfg(tmp_path, 0), runs=3, confirmed=True)
    assert anthropic_only == []
    assert result["needs_confirmation"] is False
    assert "paid calls are off" in result["reason"]


def test_an_estimate_over_the_cap_refuses(tmp_path, anthropic_only):
    result = ai_probe.run(_cfg(tmp_path, 0.10), runs=3, confirmed=True)
    assert anthropic_only == []
    assert "exceed the monthly cap" in result["reason"]


def test_a_confirmed_run_records_what_it_actually_cost(tmp_path, anthropic_only):
    cfg = _cfg(tmp_path, 10)
    result = ai_probe.run(cfg, runs=3, confirmed=True)
    assert len(anthropic_only) == 6
    assert result["cost_usd"] == pytest.approx(0.30)
    assert dataforseo.spend_this_month(cfg) == pytest.approx(0.30)


def test_the_next_estimate_is_the_median_of_real_runs(tmp_path, anthropic_only):
    cfg = _cfg(tmp_path, 10)
    for cost in (0.02, 0.04, 0.30):
        dataforseo.record_spend(
            cfg, "ai_probe", cost, detail={"anthropic": {"calls": 2, "cost_usd": cost}}
        )
    each, basis = ai_probe.per_call_estimate(cfg, "anthropic")
    # Per call: 0.01, 0.02, 0.15. The outlier does not drag the median.
    assert each == pytest.approx(0.02)
    assert "median of 3" in basis


def test_a_run_that_overshoots_stops_at_the_cap(tmp_path, anthropic_only, monkeypatch):
    cfg = _cfg(tmp_path, 0.12)
    # An estimate low enough to pass the check, then calls that cost more.
    monkeypatch.setitem(ai_probe.FIRST_RUN_ESTIMATE, "anthropic", 0.01)
    result = ai_probe.run(cfg, runs=3, confirmed=True)
    assert result["stopped_at_cap"] is True
    assert len(anthropic_only) == 3
    assert result["cost_usd"] <= 0.12 + 0.05


def test_spend_written_in_the_same_second_is_all_kept(tmp_path):
    cfg = _cfg(tmp_path, 10)
    for cost in (0.01, 0.02, 0.03):
        dataforseo.record_spend(cfg, "keywords_for_keywords", cost)
    assert dataforseo.spend_this_month(cfg) == pytest.approx(0.06)
    costs = [
        json.loads(p.read_text(encoding="utf-8"))["cost_usd"]
        for p in ai_probe.history.snapshots(cfg, "spend")
    ]
    assert costs == [0.01, 0.02, 0.03]


def test_cost_comes_from_the_response_usage():
    price = ai_probe.PRICES["anthropic"]
    assert ai_probe._tokens(price, 1_000_000, 0) == pytest.approx(price["input"])
    assert ai_probe._tokens(price, 0, 1_000_000) == pytest.approx(price["output"])

"""Module D: a refused CrUX request is a setup problem, not a quiet site.

The Chrome UX Report API answers 404 when an origin has too little traffic and
403 when the key may not call it. Both used to surface as "no field data", so a
disabled API looked like a site nobody visits. No test here touches the network.
"""

from __future__ import annotations

import httpx

import perf


class _Response:
    def __init__(self, status: int, body: dict):
        self.status_code = status
        self._body = body

    def json(self) -> dict:
        return self._body


def _answer(monkeypatch, status: int, body: dict) -> None:
    monkeypatch.setattr(perf.httpx, "post", lambda *a, **k: _Response(status, body))


def test_a_404_means_the_origin_has_no_data(monkeypatch):
    _answer(monkeypatch, 404, {"error": {"message": "chrome ux report data not found"}})
    assert perf._crux_origin("https://example.com", "k") == (None, None)


def test_a_403_names_the_setup_problem(monkeypatch):
    message = "Requests to this API chromeuxreport.googleapis.com ... are blocked."
    _answer(monkeypatch, 403, {"error": {"message": message}})
    record, problem = perf._crux_origin("https://example.com", "k")
    assert record is None
    assert "HTTP 403" in problem and "are blocked" in problem


def test_a_record_comes_back_untouched(monkeypatch):
    _answer(monkeypatch, 200, {"record": {"metrics": {}}})
    assert perf._crux_origin("https://example.com", "k") == ({"metrics": {}}, None)


def test_a_network_failure_is_reported_not_swallowed(monkeypatch):
    def fail(*a, **k):
        raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(perf.httpx, "post", fail)
    record, problem = perf._crux_origin("https://example.com", "k")
    assert record is None and "did not answer" in problem


def test_the_refusal_is_a_catalogued_finding():
    finding = perf.F.make("perf.crux_unavailable", "https://example.com", "HTTP 403")
    assert finding.to_dict()["severity"] == "warning"

"""Module D: performance.

PageSpeed Insights for lab metrics on each template URL, mobile and desktop,
plus origin-level CrUX field data when the site has enough traffic to have any.

Small sites usually have no field data at all. That is reported as a notice and
the lab numbers are labelled as lab numbers, because presenting a Lighthouse
score as what users experience is the most common way performance reporting
misleads.

Needs a PageSpeed API key, which is free. Without one the module reports why it
was skipped rather than failing the audit.
"""

from __future__ import annotations

import json
import sys

import httpx

import findings as F
import secrets

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
CRUX_ENDPOINT = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"

# Core Web Vitals thresholds at the 75th percentile.
LCP_GOOD_MS = 2500
INP_GOOD_MS = 200
CLS_GOOD = 0.1
TTFB_SLOW_MS = 800
PAGE_WEIGHT_LIMIT = 2 * 1024 * 1024

# Lighthouse audits worth a finding when they fail, mapped to our check ids.
AUDIT_CHECKS = {
    "render-blocking-resources": "perf.render_blocking",
    "uses-text-compression": "perf.text_uncompressed",
    "uses-long-cache-ttl": "perf.static_no_cache_header",
    "total-byte-weight": "perf.page_weight",
}


def _psi(url: str, strategy: str, key: str, timeout: float = 90.0) -> dict:
    params = {
        "url": url,
        "strategy": strategy,
        "key": key,
        "category": ["performance"],
    }
    response = httpx.get(PSI_ENDPOINT, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _crux_origin(origin: str, key: str, timeout: float = 30.0) -> dict | None:
    """Origin-level field data. Returns None when the origin has none."""
    try:
        response = httpx.post(
            CRUX_ENDPOINT,
            params={"key": key},
            json={"origin": origin},
            timeout=timeout,
        )
    except httpx.HTTPError:
        return None
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        return None
    return response.json().get("record")


def _metric(record: dict | None, name: str) -> float | None:
    if not record:
        return None
    metric = (record.get("metrics") or {}).get(name)
    if not metric:
        return None
    percentile = metric.get("percentiles", {}).get("p75")
    try:
        return float(percentile)
    except (TypeError, ValueError):
        return None


def run(cfg) -> dict:
    key = secrets.get("SITESEO_PAGESPEED_API_KEY")
    if not key:
        return {
            "module": "D",
            "available": False,
            "reason": (
                "no PageSpeed API key. It is free from the Google Cloud console. "
                "Store it as SITESEO_PAGESPEED_API_KEY, then run siteseo doctor."
            ),
            "findings": [],
        }

    emitted: list[F.Finding] = []
    templates: list[dict] = []

    field_record = _crux_origin(cfg.origin, key)
    has_field_data = field_record is not None

    if not has_field_data:
        emitted.append(
            F.make(
                "perf.no_field_data",
                cfg.origin,
                "the Chrome UX Report has no field data for this origin, so the numbers "
                "below are laboratory measurements rather than what real users experienced",
            )
        )
    else:
        for metric_name, check_id, threshold, unit in (
            ("largest_contentful_paint", "cwv.lcp_above_threshold", LCP_GOOD_MS, "ms"),
            ("interaction_to_next_paint", "cwv.inp_above_threshold", INP_GOOD_MS, "ms"),
            ("cumulative_layout_shift", "cwv.cls_above_threshold", CLS_GOOD, ""),
        ):
            value = _metric(field_record, metric_name)
            if value is None:
                continue
            if value > threshold:
                emitted.append(
                    F.make(
                        check_id,
                        cfg.origin,
                        f"field data: {metric_name} at the 75th percentile is "
                        f"{value}{unit}, above the {threshold}{unit} threshold",
                        group="field",
                    )
                )

    for template in cfg.templates:
        url = cfg.origin.rstrip("/") + template
        row: dict = {"template": template, "url": url}
        for strategy in ("mobile", "desktop"):
            try:
                data = _psi(url, strategy, key)
            except httpx.HTTPError as exc:
                row[strategy] = {"error": secrets.redact(str(exc))}
                continue

            lighthouse = data.get("lighthouseResult", {})
            audits = lighthouse.get("audits", {})
            row[strategy] = {
                "performance_score": (
                    lighthouse.get("categories", {}).get("performance", {}).get("score")
                ),
                "lcp_ms": _audit_ms(audits, "largest-contentful-paint"),
                "cls": _audit_number(audits, "cumulative-layout-shift"),
                "tbt_ms": _audit_ms(audits, "total-blocking-time"),
                "ttfb_ms": _audit_ms(audits, "server-response-time"),
                "bytes": _audit_number(audits, "total-byte-weight"),
            }

            if strategy != "mobile":
                continue

            ttfb = row[strategy]["ttfb_ms"]
            if ttfb and ttfb > TTFB_SLOW_MS:
                emitted.append(
                    F.make("perf.ttfb_slow", url, f"lab TTFB {ttfb:.0f} ms on mobile")
                )

            weight = row[strategy]["bytes"]
            if weight and weight > PAGE_WEIGHT_LIMIT:
                emitted.append(
                    F.make(
                        "perf.page_weight",
                        url,
                        f"lab page weight {weight / 1024 / 1024:.1f} MB on mobile",
                    )
                )

            for audit_id, check_id in AUDIT_CHECKS.items():
                if check_id == "perf.page_weight":
                    continue
                audit = audits.get(audit_id) or {}
                score = audit.get("score")
                if score is not None and score < 0.9:
                    emitted.append(
                        F.make(
                            check_id,
                            url,
                            f"Lighthouse {audit_id}: {audit.get('displayValue') or 'failing'}",
                            group=audit_id,
                        )
                    )

            # Lab CWV only counts when the origin has no field data to use.
            if not has_field_data:
                lcp = row[strategy]["lcp_ms"]
                if lcp and lcp > LCP_GOOD_MS:
                    emitted.append(
                        F.make(
                            "cwv.lcp_above_threshold",
                            url,
                            f"lab LCP {lcp:.0f} ms on mobile (no field data available)",
                            group="lab",
                        )
                    )
                cls = row[strategy]["cls"]
                if cls and cls > CLS_GOOD:
                    emitted.append(
                        F.make(
                            "cwv.cls_above_threshold",
                            url,
                            f"lab CLS {cls:.3f} on mobile (no field data available)",
                            group="lab",
                        )
                    )

        templates.append(row)

    merged = F.order(F.merge(emitted))
    return {
        "module": "D",
        "available": True,
        "site": cfg.site,
        "field_data": has_field_data,
        "templates": templates,
        "findings": [f.to_dict() for f in merged],
        "notes": [
            "Interaction to Next Paint cannot be measured in a laboratory run. It only "
            "appears when the origin has Chrome UX Report field data."
        ],
    }


def _audit_ms(audits: dict, name: str) -> float | None:
    value = (audits.get(name) or {}).get("numericValue")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _audit_number(audits: dict, name: str) -> float | None:
    return _audit_ms(audits, name)


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Module D: performance")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = run(cfg)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    if not result["available"]:
        print(f"Module D skipped: {result['reason']}")
        return 0

    print(f"Performance for {result['site']}")
    print(f"  field data: {'yes' if result['field_data'] else 'no, lab results only'}")
    print()
    for row in result["templates"]:
        mobile = row.get("mobile") or {}
        score = mobile.get("performance_score")
        print(f"  {row['template']:30s} mobile score {score if score is not None else 'n/a'}")
    print()
    for finding in result["findings"]:
        print(f"  [{finding['severity']:7s}] {finding['id']:30s} {finding['evidence'][:110]}")
    for note in result.get("notes", []):
        print(f"\nNote: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Module J: Google Search Console.

Pulls Search Analytics by query, page, country and device, sitemap status, and
URL Inspection for sitemap URLs earning no impressions. Everything lands as a
dated JSON snapshot in the site repo, so the trend survives between sessions and
between machines.

Also derives the content findings that need query data to exist at all:
cannibalization, decay, click-through outliers and striking-distance queries.
Those are module F checks, computed here because this is where the data is.

Needs a service account with access to the property. Without one the module says
so and the audit continues.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from datetime import date, timedelta

import findings as F
import history
import secrets

SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
ROW_LIMIT = 25_000
BACKFILL_MONTHS = 16
DECAY_DROP = 0.30
DECAY_MIN_CLICKS = 10
STRIKING_MIN = 8.0
STRIKING_MAX = 20.0
STRIKING_MIN_IMPRESSIONS = 50
CTR_OUTLIER_RATIO = 0.5
INSPECTION_BUDGET = 40


def _service():
    """Authorised Search Console client, or None with a reason."""
    path = secrets.get("SITESEO_GSC_SERVICE_ACCOUNT")
    if not path:
        return None, (
            "no Search Console service account. Create one, grant it access to the "
            "property, and store the JSON key path as SITESEO_GSC_SERVICE_ACCOUNT."
        )
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        return None, f"Google API client not installed: {exc}. Run siteseo setup."

    try:
        credentials = service_account.Credentials.from_service_account_file(
            path, scopes=[SCOPE]
        )
        return build("searchconsole", "v1", credentials=credentials,
                     cache_discovery=False), None
    except Exception as exc:
        return None, secrets.redact(f"could not authenticate: {exc}")


def _query(service, site: str, start: date, end: date, dimensions: list[str]) -> list[dict]:
    rows: list[dict] = []
    start_row = 0
    while True:
        body = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": dimensions,
            "rowLimit": ROW_LIMIT,
            "startRow": start_row,
        }
        response = (
            service.searchanalytics().query(siteUrl=site, body=body).execute()
        )
        batch = response.get("rows", [])
        rows.extend(batch)
        if len(batch) < ROW_LIMIT:
            break
        start_row += ROW_LIMIT
    return rows


def _property_candidates(site: str) -> list[str]:
    """Search Console accepts a URL prefix or a domain property."""
    host = site.split("://", 1)[-1].rstrip("/")
    return [site.rstrip("/") + "/", f"sc-domain:{host}", f"sc-domain:{host.removeprefix('www.')}"]


def analyse(rows_by_page_query: list[dict], prior_rows: list[dict] | None) -> list[F.Finding]:
    """Module F checks that only exist once query data does."""
    emitted: list[F.Finding] = []

    # Cannibalization: one query, several pages, both earning impressions.
    by_query: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for row in rows_by_page_query:
        query, page = row["keys"][0], row["keys"][1]
        by_query[query].append((page, row.get("impressions", 0), row.get("position", 0)))

    for query, entries in by_query.items():
        serious = [e for e in entries if e[1] >= 20]
        if len(serious) < 2:
            continue
        pages = [e[0] for e in serious]
        emitted.append(
            F.make(
                "content.cannibalization",
                pages,
                f'query "{query}" splits impressions across {len(serious)} pages: '
                + ", ".join(f"{p} ({int(i)} impressions, position {pos:.1f})"
                            for p, i, pos in serious[:3]),
                group=query,
            )
        )

    # Click-through outliers among pages that already rank well.
    ranked = [
        row for row in rows_by_page_query
        if 1 <= row.get("position", 99) <= 5 and row.get("impressions", 0) >= 50
    ]
    if len(ranked) >= 5:
        median_ctr = statistics.median(row.get("ctr", 0) for row in ranked)
        for row in ranked:
            ctr = row.get("ctr", 0)
            if median_ctr and ctr < median_ctr * CTR_OUTLIER_RATIO:
                emitted.append(
                    F.make(
                        "content.ctr_outlier",
                        row["keys"][1],
                        f'"{row["keys"][0]}" at position {row.get("position", 0):.1f} '
                        f"has {ctr * 100:.1f}% click-through against a site median of "
                        f"{median_ctr * 100:.1f}% at that position",
                        group=row["keys"][1],
                    )
                )

    # Striking distance.
    for row in rows_by_page_query:
        position = row.get("position", 99)
        if STRIKING_MIN <= position <= STRIKING_MAX and row.get("impressions", 0) >= STRIKING_MIN_IMPRESSIONS:
            emitted.append(
                F.make(
                    "content.striking_distance",
                    row["keys"][1],
                    f'"{row["keys"][0]}" sits at position {position:.1f} with '
                    f"{int(row.get('impressions', 0))} impressions",
                    group=row["keys"][0],
                )
            )

    # Decay, against the previous 28-day window.
    if prior_rows:
        now_clicks: dict[str, float] = defaultdict(float)
        was_clicks: dict[str, float] = defaultdict(float)
        for row in rows_by_page_query:
            now_clicks[row["keys"][1]] += row.get("clicks", 0)
        for row in prior_rows:
            was_clicks[row["keys"][1]] += row.get("clicks", 0)
        for page, before in was_clicks.items():
            if before < DECAY_MIN_CLICKS:
                continue
            after = now_clicks.get(page, 0)
            drop = (before - after) / before
            if drop >= DECAY_DROP:
                emitted.append(
                    F.make(
                        "content.decay",
                        page,
                        f"clicks fell from {before:.0f} to {after:.0f} "
                        f"({drop * 100:.0f}% down) across 28 days against the prior 28",
                        group=page,
                    )
                )

    return emitted


def run(cfg, *, days: int = 28, backfill: bool = False) -> dict:
    service, reason = _service()
    if service is None:
        return {
            "module": "J",
            "source": "search console",
            "available": False,
            "reason": reason,
            "findings": [F.make("gsc.not_configured", cfg.site, reason).to_dict()],
        }

    today = date.today()
    # Search Console data lags by roughly two days.
    end = today - timedelta(days=2)
    start = end - timedelta(days=(BACKFILL_MONTHS * 30) if backfill else days)
    prior_end = start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=days)

    last_error = None
    for candidate in _property_candidates(cfg.site):
        try:
            rows = _query(service, candidate, start, end, ["query", "page"])
            prior = _query(service, candidate, prior_start, prior_end, ["query", "page"])
            by_page = _query(service, candidate, start, end, ["page"])
            by_country = _query(service, candidate, start, end, ["country"])
            by_device = _query(service, candidate, start, end, ["device"])
            sitemaps = service.sitemaps().list(siteUrl=candidate).execute().get("sitemap", [])
            property_used = candidate
            break
        except Exception as exc:
            last_error = exc
            continue
    else:
        reason = secrets.redact(
            f"none of the property forms could be read: {last_error}. "
            "Confirm the service account has access in Search Console."
        )
        return {
            "module": "J",
            "source": "search console",
            "available": False,
            "reason": reason,
            "findings": [F.make("gsc.not_configured", cfg.site, reason).to_dict()],
        }

    emitted = analyse(rows, prior)

    for sitemap in sitemaps:
        errors = int(sitemap.get("errors", 0) or 0)
        if errors:
            emitted.append(
                F.make(
                    "gsc.sitemap_error",
                    sitemap.get("path", cfg.site),
                    f"Search Console reports {errors} error(s) for this sitemap",
                    group=sitemap.get("path", ""),
                )
            )

    # Sitemap URLs earning no impressions may not be indexed at all. URL
    # Inspection has a daily quota, so this samples rather than sweeping.
    earning = {row["keys"][0] for row in by_page if row.get("impressions", 0) > 0}
    inspected = 0
    for url in _sitemap_urls(cfg):
        if url in earning or inspected >= INSPECTION_BUDGET:
            continue
        inspected += 1
        try:
            report = (
                service.urlInspection()
                .index()
                .inspect(body={"inspectionUrl": url, "siteUrl": property_used})
                .execute()
            )
        except Exception:
            continue
        verdict = (
            report.get("inspectionResult", {})
            .get("indexStatusResult", {})
        )
        if verdict.get("verdict") not in {"PASS", None}:
            emitted.append(
                F.make(
                    "gsc.url_not_indexed",
                    url,
                    f"Search Console verdict {verdict.get('verdict')}: "
                    f"{verdict.get('coverageState', 'no detail given')}",
                    # Grouped by the reason, not the URL: ten pages "Discovered -
                    # currently not indexed" are one problem with ten URLs, and
                    # listing them as ten findings buried everything below them.
                    group=verdict.get("coverageState", "") or str(verdict.get("verdict")),
                )
            )

    merged = F.order(F.merge(emitted))
    return {
        "module": "J",
        "source": "search console",
        "available": True,
        "property": property_used,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "totals": _totals(rows),
        "rows_query_page": rows[:5000],
        "rows_page": by_page,
        "rows_country": by_country,
        "rows_device": by_device,
        "sitemaps": sitemaps,
        "urls_inspected": inspected,
        "findings": [f.to_dict() for f in merged],
    }


def _sitemap_urls(cfg) -> list[str]:
    """URLs from the build's sitemap, so inspection targets what we publish."""
    if not cfg.build_path:
        return []
    path = cfg.build_path / "sitemap.xml"
    if not path.is_file():
        return []
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(path.read_bytes())
    except ET.ParseError:
        return []
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    found = [node.text.strip() for node in root.findall(".//sm:loc", namespace) if node.text]
    return found or [node.text.strip() for node in root.findall(".//loc") if node.text]


def _totals(rows: list[dict]) -> dict:
    return {
        "rows": len(rows),
        "clicks": round(sum(r.get("clicks", 0) for r in rows), 1),
        "impressions": round(sum(r.get("impressions", 0) for r in rows), 1),
        "queries": len({r["keys"][0] for r in rows}),
        "pages": len({r["keys"][1] for r in rows}),
    }


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Module J: Search Console")
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--backfill", action="store_true", help="pull 16 months on first run")
    parser.add_argument("--no-snapshot", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = run(cfg, days=args.days, backfill=args.backfill)

    if result["available"] and not args.no_snapshot:
        result["snapshot"] = str(history.write(cfg, "gsc", result))

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    if not result["available"]:
        print(f"Search Console unavailable: {result['reason']}")
        return 0

    totals = result["totals"]
    print(f"Search Console: {result['property']}")
    print(f"  window      {result['window']['start']} to {result['window']['end']}")
    print(f"  clicks      {totals['clicks']:.0f}")
    print(f"  impressions {totals['impressions']:.0f}")
    print(f"  queries     {totals['queries']}")
    print(f"  pages       {totals['pages']}")
    print()
    for finding in result["findings"]:
        print(f"  [{finding['severity']:7s}] {finding['id']:30s} {finding['evidence'][:120]}")
    if "snapshot" in result:
        print(f"\nSnapshot: {result['snapshot']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

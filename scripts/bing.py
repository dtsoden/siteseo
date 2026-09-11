"""Module J: Bing Webmaster Tools, plus the Bing AI Performance CSV import.

The query and crawl data come from the Webmaster API. The AI Performance report,
which shows citations and grounding queries across Copilot and Bing AI answers,
has no confirmed public API, so it is imported from CSV exports dropped into
.siteseo/imports/bing-ai/. Those grounding queries matter beyond Bing: they are
real questions that already retrieved your pages, which makes them the best
possible seed for the module K prompt set.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import httpx

import findings as F
import history
import secrets

API_ROOT = "https://ssl.bing.com/webmaster/api.svc/json"


def _call(method: str, key: str, params: dict, timeout: float = 45.0) -> dict | None:
    try:
        response = httpx.get(
            f"{API_ROOT}/{method}",
            params={**params, "apikey": key},
            timeout=timeout,
        )
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def import_ai_performance(cfg) -> dict:
    """Read Bing AI Performance CSV exports, if any have been dropped in."""
    folder = cfg.imports_dir / "bing-ai"
    result: dict = {"folder": str(folder), "files": [], "grounding_queries": [], "rows": 0}
    if not folder.is_dir():
        return result

    for path in sorted(folder.glob("*.csv")):
        result["files"].append(path.name)
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    result["rows"] += 1
                    for column in ("Query", "query", "Grounding Query", "Keyword"):
                        value = (row.get(column) or "").strip()
                        if value:
                            result["grounding_queries"].append(value)
                            break
        except (OSError, csv.Error) as exc:
            result.setdefault("errors", []).append(f"{path.name}: {exc}")

    # Keep them unique and stable in order, so the prompt set does not churn.
    seen: set[str] = set()
    ordered: list[str] = []
    for query in result["grounding_queries"]:
        if query.lower() not in seen:
            seen.add(query.lower())
            ordered.append(query)
    result["grounding_queries"] = ordered
    return result


def run(cfg) -> dict:
    ai_import = import_ai_performance(cfg)
    key = secrets.get("SITESEO_BING_API_KEY")

    if not key:
        reason = (
            "no Bing Webmaster API key. Generate one in Bing Webmaster Tools under "
            "Settings, API access, and store it as SITESEO_BING_API_KEY."
        )
        return {
            "module": "J",
            "source": "bing",
            "available": False,
            "reason": reason,
            "ai_performance_import": ai_import,
            "findings": [F.make("bing.not_configured", cfg.site, reason).to_dict()],
        }

    site = cfg.site.rstrip("/") + "/"
    emitted: list[F.Finding] = []

    stats = _call("GetRankAndTrafficStats", key, {"siteUrl": site})
    queries = _call("GetQueryStats", key, {"siteUrl": site})
    pages = _call("GetPageStats", key, {"siteUrl": site})
    crawl_issues = _call("GetCrawlIssues", key, {"siteUrl": site})

    if stats is None and queries is None:
        reason = (
            "the Bing Webmaster API did not answer. Check the key and that the site "
            "is verified in Bing Webmaster Tools."
        )
        return {
            "module": "J",
            "source": "bing",
            "available": False,
            "reason": reason,
            "ai_performance_import": ai_import,
            "findings": [F.make("bing.not_configured", cfg.site, reason).to_dict()],
        }

    issues = (crawl_issues or {}).get("d", []) or []
    for issue in issues[:50]:
        url = issue.get("Url") or site
        code = issue.get("HttpCode")
        if code and int(code) >= 500:
            emitted.append(
                F.make("http.status_5xx", url, f"Bing recorded HTTP {code} crawling this URL",
                       group=url)
            )
        elif code and 400 <= int(code) < 500:
            emitted.append(
                F.make("http.status_4xx", url, f"Bing recorded HTTP {code} crawling this URL",
                       group=url)
            )

    merged = F.order(F.merge(emitted))
    return {
        "module": "J",
        "source": "bing",
        "available": True,
        "site": site,
        "traffic": (stats or {}).get("d", []),
        "queries": (queries or {}).get("d", [])[:2000],
        "pages": (pages or {}).get("d", [])[:2000],
        "crawl_issues": issues[:200],
        "ai_performance_import": ai_import,
        "findings": [f.to_dict() for f in merged],
    }


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Module J: Bing Webmaster Tools")
    parser.add_argument("--no-snapshot", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = run(cfg)
    if result["available"] and not args.no_snapshot:
        result["snapshot"] = str(history.write(cfg, "bing", result))

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    imported = result["ai_performance_import"]
    if not result["available"]:
        print(f"Bing Webmaster unavailable: {result['reason']}")
    else:
        print(f"Bing Webmaster: {result['site']}")
        print(f"  queries      {len(result['queries'])}")
        print(f"  pages        {len(result['pages'])}")
        print(f"  crawl issues {len(result['crawl_issues'])}")

    print()
    print(f"AI Performance CSV import from {imported['folder']}")
    if imported["files"]:
        print(f"  {len(imported['files'])} file(s), {imported['rows']} rows, "
              f"{len(imported['grounding_queries'])} unique grounding queries")
        print("  These seed the module K prompt set: they already retrieved your pages.")
    else:
        print("  no files yet. Export AI Performance from Bing Webmaster Tools and")
        print("  drop the CSV here. There is no confirmed public API for this report.")

    for finding in result["findings"]:
        print(f"\n  [{finding['severity']}] {finding['id']}: {finding['evidence'][:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


_ = Path

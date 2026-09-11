"""Modules L and M: paid research and backlinks.

Off by default. Every call prints its estimated cost and what remains of the
monthly budget, and stops rather than exceeding it. Spend is recorded in the
site repo alongside everything else, so the running total survives between
machines.

Module M prefers free sources. Your own links come from Search Console and
Ahrefs free tier CSV exports you drop into .siteseo/imports/. Only competitor
links need a paid call. No toxicity scoring is performed and no disavow file is
ever generated: Google's own position is that most sites should never use
disavow.
"""

from __future__ import annotations

import base64
import csv
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

import findings as F
import history
import secrets

API_ROOT = "https://api.dataforseo.com/v3"
TIMEOUT = 120.0

# Published list prices per request, used for the estimate shown before a call.
# Verified against the vendor's pricing page on the date below; the estimate is
# always labelled as an estimate, and the response carries the real cost.
COSTS_VERIFIED = "2026-09-11"
ESTIMATES = {
    "keywords_for_keywords": 0.05,
    "ranked_keywords": 0.11,
    "serp_organic": 0.003,
    "backlinks_summary": 0.02,
    "backlinks_referring_domains": 0.02,
    "domain_intersection": 0.11,
}


class BudgetExceeded(RuntimeError):
    pass


def _auth() -> str:
    login = secrets.require("SITESEO_DATAFORSEO_LOGIN")
    password = secrets.require("SITESEO_DATAFORSEO_PASSWORD")
    return base64.b64encode(f"{login}:{password}".encode()).decode()


def spend_this_month(cfg) -> float:
    """Total recorded spend for the current calendar month."""
    prefix = date.today().strftime("%Y-%m")
    total = 0.0
    for path in history.snapshots(cfg, "spend"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if str(record.get("recorded_at", "")).startswith(prefix):
            total += float(record.get("cost_usd", 0) or 0)
    return round(total, 4)


def budget_check(cfg, estimate: float) -> tuple[bool, str]:
    cap = cfg.budget.monthly_usd
    spent = spend_this_month(cfg)
    remaining = cap - spent
    message = (
        f"estimated cost ${estimate:.4f}. "
        f"Spent ${spent:.2f} of ${cap:.2f} this month, ${remaining:.2f} remaining."
    )
    if cap <= 0:
        return False, (
            "budget.monthly_usd is 0 in siteseo.yaml, so paid calls are off. "
            "Raise it to enable module L and competitor backlinks. " + message
        )
    if estimate > remaining:
        return False, "this call would exceed the monthly cap. " + message
    return True, message


def record_spend(cfg, endpoint: str, cost: float) -> None:
    history.write(
        cfg,
        "spend",
        {
            "endpoint": endpoint,
            "cost_usd": round(float(cost), 6),
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )


def call(cfg, path: str, payload: list[dict], estimate_key: str, *, confirmed: bool) -> dict:
    estimate = ESTIMATES.get(estimate_key, 0.10)
    allowed, message = budget_check(cfg, estimate)
    if not allowed:
        raise BudgetExceeded(message)
    if not confirmed:
        raise BudgetExceeded(
            f"{message}\nRe-run with --confirm to make the call."
        )

    response = httpx.post(
        f"{API_ROOT}/{path}",
        headers={"Authorization": f"Basic {_auth()}", "Content-Type": "application/json"},
        json=payload,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    record_spend(cfg, path, data.get("cost", estimate))
    return data


def _tasks(data: dict) -> list[dict]:
    out = []
    for task in data.get("tasks", []) or []:
        for result in task.get("result", []) or []:
            out.append(result)
    return out


# ---------------------------------------------------------------- module L


def research(cfg, term: str, *, confirmed: bool, location: int = 2840,
             language: str = "en") -> dict:
    payload = [{
        "keywords": [term],
        "location_code": location,
        "language_code": language,
        "limit": 200,
    }]
    data = call(cfg, "dataforseo_labs/google/keyword_ideas/live", payload,
                "keywords_for_keywords", confirmed=confirmed)

    ideas = []
    for result in _tasks(data):
        for item in result.get("items", []) or []:
            info = item.get("keyword_info") or {}
            ideas.append({
                "keyword": item.get("keyword"),
                "search_volume": info.get("search_volume"),
                "competition": info.get("competition"),
                "cpc": info.get("cpc"),
                "difficulty": (item.get("keyword_properties") or {}).get(
                    "keyword_difficulty"
                ),
            })

    return {
        "module": "L",
        "term": term,
        "cost_usd": data.get("cost"),
        "ideas": sorted(ideas, key=lambda row: -(row["search_volume"] or 0))[:200],
        "spend_this_month": spend_this_month(cfg),
        "findings": [],
    }


# ---------------------------------------------------------------- module M


def import_own_links(cfg) -> dict:
    """Read CSV exports of your own links. Free, and the preferred source."""
    folder = cfg.imports_dir / "backlinks"
    result: dict = {"folder": str(folder), "files": [], "referring_domains": [], "rows": 0}
    if not folder.is_dir():
        return result

    domains: set[str] = set()
    for path in sorted(folder.glob("*.csv")):
        result["files"].append(path.name)
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    result["rows"] += 1
                    for column in (
                        "Referring page URL", "Domain", "referring_domain",
                        "Source", "Linking site", "domain_from",
                    ):
                        value = (row.get(column) or "").strip()
                        if value:
                            host = value.split("//")[-1].split("/")[0].lower()
                            if host:
                                domains.add(host)
                            break
        except (OSError, csv.Error) as exc:
            result.setdefault("errors", []).append(f"{path.name}: {exc}")

    result["referring_domains"] = sorted(domains)
    return result


def backlinks(cfg) -> dict:
    own = import_own_links(cfg)
    emitted: list[F.Finding] = []

    prior = history.latest(cfg, "backlinks")
    if prior:
        before = set(prior.get("referring_domains", []))
        now = set(own["referring_domains"])
        lost = sorted(before - now)
        if lost:
            emitted.append(
                F.make(
                    "backlinks.lost_referring_domains",
                    cfg.site,
                    f"{len(lost)} referring domain(s) present in the previous import are "
                    f"absent from this one: {', '.join(lost[:8])}",
                )
            )

    if not own["referring_domains"]:
        emitted.append(
            F.make(
                "backlinks.no_data",
                cfg.site,
                f"no backlink CSV exports found in {own['folder']}. Export the Search "
                "Console links report, or an Ahrefs free tier export, and drop it there.",
            )
        )

    return {
        "module": "M",
        "site": cfg.site,
        "referring_domains": own["referring_domains"],
        "import": own,
        "findings": [f.to_dict() for f in F.order(F.merge(emitted))],
        "notes": [
            "No toxicity scoring and no disavow file. Google's position is that most "
            "sites should never use disavow, so it is worth considering only when "
            "Search Console reports a manual action."
        ],
    }


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Modules L and M: research and backlinks")
    sub = parser.add_subparsers(dest="command", required=True)

    keywords = sub.add_parser("keywords", help="keyword ideas for a term (paid)")
    keywords.add_argument("term")
    keywords.add_argument("--confirm", action="store_true", help="authorise the paid call")

    sub.add_parser("backlinks", help="your own referring domains from CSV imports (free)")
    sub.add_parser("budget", help="show spend against the monthly cap")

    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.command == "budget":
        spent = spend_this_month(cfg)
        cap = cfg.budget.monthly_usd
        print(f"Spent ${spent:.2f} of ${cap:.2f} this month, ${cap - spent:.2f} remaining.")
        print(f"Price estimates last verified {COSTS_VERIFIED} against the vendor's "
              "published pricing. The response carries the real cost.")
        return 0

    if args.command == "backlinks":
        result = backlinks(cfg)
        if args.json:
            print(json.dumps(result, indent=2))
            return 0
        print(f"Referring domains for {cfg.site}: {len(result['referring_domains'])}")
        for domain in result["referring_domains"][:40]:
            print(f"  {domain}")
        for finding in result["findings"]:
            print(f"\n  [{finding['severity']}] {finding['id']}: {finding['evidence'][:160]}")
        for note in result["notes"]:
            print(f"\nNote: {note}")
        history.write(cfg, "backlinks", result)
        return 0

    try:
        result = research(cfg, args.term, confirmed=args.confirm)
    except BudgetExceeded as exc:
        print(f"Not calling out: {exc}")
        return 1
    except secrets.MissingSecret as exc:
        print(str(exc))
        return 1
    except httpx.HTTPError as exc:
        print(f"Request failed: {secrets.redact(str(exc))}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f"Keyword ideas for {result['term']}  (cost ${result['cost_usd']})")
    print(f"{'volume':>8s}  {'difficulty':>10s}  keyword")
    for row in result["ideas"][:40]:
        print(f"{row['search_volume'] or 0:8d}  {str(row['difficulty'] or '-'):>10s}  {row['keyword']}")
    print(f"\nSpent ${result['spend_this_month']:.2f} this month.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


_ = Path

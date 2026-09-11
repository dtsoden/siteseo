"""Module N: Google Analytics 4.

What happens on the site once someone arrives, which is the half Search Console
cannot see. Search Console says a page earned 400 impressions and 12 clicks.
Analytics says those 12 visitors left in nine seconds. Only together do they say
anything useful.

Read-only. The service account needs Viewer on the GA4 property, granted in the
Analytics admin screen, not in Cloud Console.

Also separates AI assistant referrals from ordinary search traffic, because
"someone arrived from ChatGPT" is the only first-party evidence that AI
visibility work is doing anything.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta

import findings as F
import history
import secrets

SCOPE = "https://www.googleapis.com/auth/analytics.readonly"

#: Referrer hosts that mean an AI assistant sent the visitor.
AI_SOURCES = {
    "chatgpt.com": "ChatGPT",
    "chat.openai.com": "ChatGPT",
    "perplexity.ai": "Perplexity",
    "claude.ai": "Claude",
    "gemini.google.com": "Gemini",
    "copilot.microsoft.com": "Copilot",
    "bing.com": "Bing",
    "you.com": "You.com",
}


def _clients():
    """Analytics Data and Admin clients, or None with a reason."""
    path = secrets.get("SITESEO_GSC_SERVICE_ACCOUNT")
    if not path:
        return None, None, (
            "no service account. Store one with: aihsm put SITESEO_GSC_SERVICE_ACCOUNT"
        )
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        return None, None, f"Google API client not installed: {exc}. Run /siteseo setup."

    try:
        credentials = service_account.Credentials.from_service_account_file(
            path, scopes=[SCOPE]
        )
        data = build("analyticsdata", "v1beta", credentials=credentials,
                     cache_discovery=False)
        admin = build("analyticsadmin", "v1beta", credentials=credentials,
                      cache_discovery=False)
        return data, admin, None
    except Exception as exc:
        return None, None, secrets.redact(f"could not authenticate: {exc}")


def find_property(admin, site: str) -> tuple[str | None, str]:
    """The GA4 property for this site, discovered rather than configured.

    Returns (property id, note). Asking the user to paste a property id is one
    more thing to get wrong when the service account can just be asked what it
    can see.
    """
    try:
        summaries = admin.accountSummaries().list(pageSize=200).execute()
    except Exception as exc:
        return None, secrets.redact(
            f"could not list Analytics properties: {exc}. Add "
            f"{_account_email()} as a Viewer in the Analytics admin screen."
        )

    found: list[tuple[str, str]] = []
    for account in summaries.get("accountSummaries", []) or []:
        for prop in account.get("propertySummaries", []) or []:
            found.append((prop.get("property", ""), prop.get("displayName", "")))

    if not found:
        return None, (
            f"the service account can see no Analytics properties. Add "
            f"{_account_email()} as a Viewer in Analytics admin, Property access management."
        )

    host = site.split("://", 1)[-1].strip("/").lower()
    for property_id, name in found:
        if host in name.lower() or host.removeprefix("www.") in name.lower():
            return property_id, f"matched {name}"

    return found[0][0], (
        f"no property name matched {host}, using {found[0][1]}. "
        f"Properties visible: {', '.join(name for _, name in found[:5])}"
    )


def _account_email() -> str:
    path = secrets.get("SITESEO_GSC_SERVICE_ACCOUNT")
    if not path:
        return "the service account"
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle).get("client_email", "the service account")
    except Exception:
        return "the service account"


def _report(data, property_id: str, dimensions: list[str], metrics: list[str],
            start: date, end: date, limit: int = 500) -> list[dict]:
    body = {
        "dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
        "dimensions": [{"name": d} for d in dimensions],
        "metrics": [{"name": m} for m in metrics],
        "limit": limit,
    }
    response = data.properties().runReport(property=property_id, body=body).execute()
    rows = []
    for row in response.get("rows", []) or []:
        entry = {}
        for name, value in zip(dimensions, row.get("dimensionValues", [])):
            entry[name] = value.get("value")
        for name, value in zip(metrics, row.get("metricValues", [])):
            raw = value.get("value")
            try:
                entry[name] = float(raw)
            except (TypeError, ValueError):
                entry[name] = raw
        rows.append(entry)
    return rows


def run(cfg, *, days: int = 28) -> dict:
    data, admin, reason = _clients()
    if data is None:
        return {"module": "N", "source": "analytics", "available": False,
                "reason": reason, "findings": []}

    property_id, note = find_property(admin, cfg.site)
    if property_id is None:
        return {"module": "N", "source": "analytics", "available": False,
                "reason": note, "findings": []}

    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)

    try:
        pages = _report(
            data, property_id, ["pagePath"],
            ["screenPageViews", "activeUsers", "userEngagementDuration", "bounceRate"],
            start, end,
        )
        sources = _report(
            data, property_id, ["sessionSource", "sessionMedium"],
            ["sessions", "activeUsers"], start, end, limit=200,
        )
        totals = _report(data, property_id, [], ["sessions", "activeUsers",
                                                "screenPageViews"], start, end, limit=1)
    except Exception as exc:
        return {"module": "N", "source": "analytics", "available": False,
                "reason": secrets.redact(f"report failed: {exc}"), "findings": []}

    ai_referrals: dict[str, float] = {}
    organic = 0.0
    for row in sources:
        source = (row.get("sessionSource") or "").lower()
        sessions = row.get("sessions") or 0
        if (row.get("sessionMedium") or "").lower() == "organic":
            organic += sessions
        for host, label in AI_SOURCES.items():
            if host in source:
                ai_referrals[label] = ai_referrals.get(label, 0) + sessions
                break

    emitted: list[F.Finding] = []
    if not ai_referrals:
        emitted.append(
            F.make(
                "ai_vis.no_referrals",
                cfg.site,
                f"no sessions from an AI assistant in the last {days} days, "
                f"across {int(sum(r.get('sessions', 0) for r in sources))} sessions",
            )
        )

    return {
        "module": "N",
        "source": "analytics",
        "available": True,
        "property": property_id,
        "property_note": note,
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "totals": totals[0] if totals else {},
        "organic_sessions": organic,
        "ai_referrals": dict(sorted(ai_referrals.items(), key=lambda kv: -kv[1])),
        "pages": sorted(pages, key=lambda r: -(r.get("screenPageViews") or 0)),
        "sources": sorted(sources, key=lambda r: -(r.get("sessions") or 0))[:50],
        "findings": [f.to_dict() for f in F.order(F.merge(emitted))],
    }


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Module N: Google Analytics 4")
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--no-snapshot", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = run(cfg, days=args.days)
    if result["available"] and not args.no_snapshot:
        result["snapshot"] = str(history.write(cfg, "analytics", result))

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    if not result["available"]:
        print(f"Analytics unavailable: {result['reason']}")
        return 0

    totals = result["totals"]
    print(f"Analytics for {cfg.site}  ({result['property_note']})")
    print(f"  window   {result['window']['start']} to {result['window']['end']}")
    print(f"  sessions {int(totals.get('sessions', 0))}")
    print(f"  users    {int(totals.get('activeUsers', 0))}")
    print(f"  organic  {int(result['organic_sessions'])} sessions")
    print()
    print("  AI assistant referrals:")
    if result["ai_referrals"]:
        for label, count in result["ai_referrals"].items():
            print(f"    {label:12s} {int(count)}")
    else:
        print("    none in this window")
    print()
    print("  Top pages by views:")
    for row in result["pages"][:12]:
        views = int(row.get("screenPageViews") or 0)
        users = int(row.get("activeUsers") or 0)
        print(f"    {views:6d} views  {users:5d} users  {row.get('pagePath', '')[:60]}")
    if "snapshot" in result:
        print(f"\nSnapshot: {result['snapshot']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

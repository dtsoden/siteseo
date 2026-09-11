"""Pull every first-party data source into dated history.

What `/siteseo pull` drives. Search Console, Analytics, Bing and any CSV imports
sitting in `.siteseo/imports/`, each written as its own dated snapshot in the
site repo so the trend follows the repository between machines.

Sources that are not configured report why and are skipped. A machine with only
Search Console set up still gets Search Console.
"""

from __future__ import annotations

import json
import sys

import history


def run(cfg, *, days: int = 28, backfill: bool = False) -> dict:
    import analytics as analytics_module
    import bing as bing_module
    import gsc as gsc_module
    import logs as logs_module

    sources: dict[str, dict] = {}

    sources["search_console"] = gsc_module.run(cfg, days=days, backfill=backfill)
    sources["analytics"] = analytics_module.run(cfg, days=days)
    sources["bing"] = bing_module.run(cfg)
    sources["logs"] = logs_module.run(cfg)

    written: dict[str, str] = {}
    for name, result in sources.items():
        if result.get("available"):
            kind = {"search_console": "gsc", "analytics": "analytics",
                    "bing": "bing", "logs": "logs"}[name]
            written[name] = str(history.write(cfg, kind, result))

    return {"sources": sources, "written": written}


def render(result: dict) -> str:
    lines = ["siteseo pull", ""]

    for name, source in result["sources"].items():
        label = name.replace("_", " ")
        if not source.get("available"):
            lines.append(f"  skipped  {label}")
            lines.append(f"           {source.get('reason', 'no reason given')[:160]}")
            continue

        lines.append(f"  ok       {label}")
        if name == "search_console":
            totals = source.get("totals", {})
            lines.append(
                f"           {int(totals.get('clicks', 0))} clicks, "
                f"{int(totals.get('impressions', 0))} impressions, "
                f"{totals.get('queries', 0)} queries, {totals.get('pages', 0)} pages"
            )
        elif name == "analytics":
            totals = source.get("totals", {})
            referrals = source.get("ai_referrals") or {}
            lines.append(
                f"           {int(totals.get('sessions', 0))} sessions, "
                f"{int(totals.get('activeUsers', 0))} users, "
                f"{int(source.get('organic_sessions', 0))} organic"
            )
            lines.append(
                "           AI referrals: "
                + (", ".join(f"{k} {int(v)}" for k, v in referrals.items())
                   if referrals else "none in this window")
            )
        elif name == "bing":
            lines.append(f"           {len(source.get('queries', []))} queries")
        elif name == "logs":
            lines.append(
                f"           {source.get('lines_read', 0)} log lines, "
                f"{len(source.get('bots', {}))} crawlers seen"
            )

    lines.append("")
    if result["written"]:
        lines.append(f"{len(result['written'])} snapshot(s) written:")
        for name, path in result["written"].items():
            lines.append(f"  {path}")
        lines.append("")
        lines.append("Commit .siteseo/ so the trend travels with the repo.")
    else:
        lines.append("Nothing was written: no source is configured yet.")
        lines.append("See the README section on connecting Google.")
    return "\n".join(lines)


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Pull first-party data into history")
    parser.add_argument("--days", type=int, default=28)
    parser.add_argument("--backfill", action="store_true",
                        help="pull 16 months of Search Console on the first run")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = run(cfg, days=args.days, backfill=args.backfill)
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0 if result["written"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

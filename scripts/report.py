"""Render an audit snapshot as markdown, with the diff against the previous run.

Findings are grouped by fix rather than by URL. One template change that clears
forty URLs appears once, with its URL list collapsed behind a count. A report
that lists the same problem forty times buries the other thirty-nine problems.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import history
import score as score_module

SEVERITY_LABEL = {"error": "Errors", "warning": "Warnings", "notice": "Notices"}
URL_PREVIEW = 8


def render(snapshot: dict, prior: dict | None = None) -> str:
    site = snapshot.get("site", "unknown site")
    when = snapshot.get("recorded_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    findings = snapshot.get("findings", [])
    scores = snapshot.get("scores", {})
    stats = snapshot.get("stats", {})

    out: list[str] = []
    out.append(f"# siteseo report: {site}")
    out.append("")
    out.append(f"Run at {when} against {snapshot.get('source', 'unknown source')}.")
    out.append("")

    # -- scores
    out.append("## Scores")
    out.append("")
    out.append("```")
    out.append(score_module.render(scores, (prior or {}).get("scores")))
    out.append("```")
    out.append("")

    agent = snapshot.get("agent_readiness")
    if agent:
        out.extend(_render_agent_readiness(agent, (prior or {}).get("agent_readiness")))

    out.extend(_render_what_was_checked(snapshot))
    if snapshot.get("bots"):
        out.extend(_render_crawlers(snapshot["bots"]))

    # -- what changed
    if prior is not None:
        delta = history.diff_findings(findings, prior.get("findings", []))
        out.append("## Since the previous run")
        out.append("")
        if not delta["new"] and not delta["resolved"]:
            out.append("Nothing changed.")
        else:
            if delta["resolved"]:
                out.append(f"Resolved ({len(delta['resolved'])}):")
                out.append("")
                for finding in _order(delta["resolved"]):
                    out.append(f"- {finding['id']} ({finding['severity']})")
                out.append("")
            if delta["new"]:
                out.append(f"New ({len(delta['new'])}):")
                out.append("")
                for finding in _order(delta["new"]):
                    out.append(f"- {finding['id']} ({finding['severity']}): {finding['evidence'][:120]}")
                out.append("")
        out.append("")

    # -- coverage
    if stats:
        out.append("## Coverage")
        out.append("")
        out.append("| Measure | Value |")
        out.append("| --- | --- |")
        for key, value in stats.items():
            out.append(f"| {key.replace('_', ' ')} | {value} |")
        out.append("")

    # -- findings, grouped by fix
    counts = {"error": 0, "warning": 0, "notice": 0}
    for finding in findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1

    out.append("## Findings")
    out.append("")
    out.append(
        f"{counts['error']} errors, {counts['warning']} warnings, {counts['notice']} notices."
    )
    out.append("")

    for severity in ("error", "warning", "notice"):
        band = [f for f in findings if f["severity"] == severity]
        if not band:
            continue
        out.append(f"### {SEVERITY_LABEL[severity]}")
        out.append("")
        for finding in _order(band):
            out.extend(_render_finding(finding))
        out.append("")

    # -- data sections
    for section in ("search_performance", "ai_visibility"):
        block = snapshot.get(section)
        if block:
            out.append(f"## {section.replace('_', ' ').title()}")
            out.append("")
            out.append("```")
            out.append(json.dumps(block, indent=2)[:4000])
            out.append("```")
            out.append("")

    # The brief goes last, addressed to whoever maintains the site.
    import brief as brief_module

    out.append(
        brief_module.render(
            snapshot,
            gsc=snapshot.get("search_performance"),
            analytics=snapshot.get("analytics"),
        )
    )

    notes = snapshot.get("notes") or []
    if notes:
        out.append("## Notes")
        out.append("")
        for note in notes:
            out.append(f"- {note}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


MODULES = {
    "A": "Crawl and indexability",
    "B": "On-page",
    "C": "Structured data",
    "D": "Performance",
    "E": "AI crawler access",
    "F": "Content quality",
    "G": "Internal linking",
    "H": "International",
    "I": "Local",
    "J": "Search Console and Bing",
    "K": "AI visibility",
    "L": "Keyword research",
    "M": "Backlinks",
    "N": "Analytics",
    "O": "Agent readiness",
}

#: Modules an audit never runs, and what does run them.
NOT_IN_AUDIT = {
    "F": "judged page by page by the seo-content agent, not by a script",
    "K": "costs model API calls, so it runs only with /siteseo track",
    "L": "paid, so it runs only with /siteseo research after a cost estimate",
    "M": "reads CSV exports you drop into .siteseo/imports/backlinks/",
}


def _render_what_was_checked(snapshot: dict) -> list[str]:
    """Every module, what it found, and why any of them did not run.

    A findings list only shows what is wrong. This table is what shows the rest:
    which areas came back clean, which were skipped and what would turn them on.
    """
    findings = snapshot.get("findings", [])
    ran = set(snapshot.get("modules") or [])
    skipped: dict[str, str] = {}
    for item in snapshot.get("skipped") or []:
        head, _, reason = item.partition(":")
        letter = head.strip().split(" ")[1] if head.strip().startswith("module ") else ""
        if letter:
            skipped[letter] = reason.strip()

    out = ["## What was checked", "", "| Module | Area | Result |", "| --- | --- | --- |"]
    for letter, area in MODULES.items():
        mine = [f for f in findings if f.get("module") == letter]
        if letter in skipped:
            result = f"not run: {skipped[letter]}"
        elif letter in NOT_IN_AUDIT and letter not in ran:
            result = f"not part of the audit: {NOT_IN_AUDIT[letter]}"
        elif letter not in ran:
            result = "not run"
        elif not mine:
            result = "checked, nothing found"
        else:
            tally = {s: sum(1 for f in mine if f["severity"] == s) for s in ("error", "warning", "notice")}
            result = ", ".join(f"{n} {s}{'s' if n != 1 else ''}" for s, n in tally.items() if n)
        out.append(f"| {letter} | {area} | {result} |")
    out.append("")
    return out


def _render_crawlers(bots: list[dict]) -> list[str]:
    out = [
        "## AI crawlers",
        "",
        "What each crawler is allowed to do, what robots.txt says, and what the site "
        "actually returned when asked with that crawler's user agent.",
        "",
        "| Crawler | Operator | Used for | Your policy | robots.txt | Fetch | Matches policy |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for bot in bots:
        statuses = set((bot.get("fetch_statuses") or {}).values())
        if not bot.get("fetch_tested"):
            fetch = "not tested"
        else:
            fetch = "200" if statuses == {200} else ", ".join(str(s) for s in sorted(statuses))
        out.append(
            f"| {bot['token']} | {bot['operator']} | {bot['purpose'].replace('_', ' ')} | "
            f"{bot['intended']} | {'allowed' if bot['robots_allowed'] else 'blocked'} | "
            f"{fetch} | {'yes' if bot['matches_policy'] else 'no'} |"
        )
    out.append("")
    return out


def _render_agent_readiness(agent: dict, prior: dict | None) -> list[str]:
    """Module O's level and checks, kept apart from the two scores."""
    out = ["## Agent readiness", ""]
    line = f"Level {agent['level']} of 5, {agent['level_name']}."
    if prior and prior.get("level") is not None and prior["level"] != agent["level"]:
        line += f" Was level {prior['level']} on the previous run."
    out.append(
        f"{line} Profile `{agent['profile']}`, measured against "
        f"{'the live site' if agent['source_kind'] == 'live' else 'build output'}."
    )
    out.append("")
    out.append(
        "This follows the ladder Cloudflare's Agent Readiness scanner publishes. It is "
        "reported on its own, never moves search health or AI access, and has no effect "
        "on Google Search."
    )
    out.append("")
    if agent.get("ceiling"):
        out.append(f"The level {agent['ceiling']}.")
        out.append("")
    upcoming = agent.get("next_level")
    if upcoming:
        out.append(
            f"Level {upcoming['level']}, {upcoming['name']}, needs {upcoming['rule']}: "
            + ", ".join(upcoming["needs"]) + "."
        )
        out.append("")

    out.append("| Check | Status | Detail |")
    out.append("| --- | --- | --- |")
    for check in agent.get("checks", []):
        detail = str(check.get("summary", "")).replace("|", "\\|")
        out.append(f"| {check['label']} | {check['status']} | {detail} |")
    out.append("")
    return out


def _order(findings: list[dict]) -> list[dict]:
    rank = {"error": 0, "warning": 1, "notice": 2}
    return sorted(
        findings,
        key=lambda f: (rank.get(f["severity"], 9), f.get("module", "Z"), f["id"]),
    )


def _render_finding(finding: dict) -> list[str]:
    urls = finding.get("urls", [])
    out = [f"#### `{finding['id']}`"]
    out.append("")
    out.append(f"Module {finding.get('module', '?')}. {finding.get('fix', '')}")
    out.append("")
    out.append(f"Evidence: {finding['evidence']}")
    out.append("")
    if finding.get("autofix"):
        out.append(f"Fixable automatically: `siteseo fix {finding['id']}`")
        out.append("")
    if len(urls) == 1:
        out.append(f"URL: {urls[0]}")
    elif urls:
        out.append(f"<details><summary>{len(urls)} URLs</summary>")
        out.append("")
        for url in urls[:URL_PREVIEW]:
            out.append(f"- {url}")
        if len(urls) > URL_PREVIEW:
            out.append(f"- and {len(urls) - URL_PREVIEW} more")
        out.append("")
        out.append("</details>")
    out.append("")
    out.append(f"Source: {finding.get('source', '')}")
    out.append("")
    return out


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Render the latest audit snapshot")
    parser.add_argument("--kind", default="audit", help="snapshot kind to render")
    parser.add_argument("--write", action="store_true", help="save under .siteseo/reports/")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    snapshot = history.latest(cfg, args.kind)
    if snapshot is None:
        print(
            f"No {args.kind} snapshot found under {cfg.history_dir}.\n"
            "Run an audit first: siteseo run audit.py",
            file=sys.stderr,
        )
        return 1

    text = render(snapshot, history.previous(cfg, args.kind))

    if args.write:
        cfg.ensure_dir(cfg.reports_dir)
        stamp = snapshot.get("recorded_at", "")[:10] or "report"
        path = cfg.reports_dir / f"{stamp}-{args.kind}.md"
        path.write_text(text, encoding="utf-8")
        print(f"Wrote {path}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

    notes = snapshot.get("notes") or []
    if notes:
        out.append("## Notes")
        out.append("")
        for note in notes:
            out.append(f"- {note}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


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

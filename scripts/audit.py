"""Full audit: run the modules, merge findings, score, and snapshot.

This is what `/siteseo audit` drives. It runs the collecting modules, keeps both
scores apart, writes a dated snapshot into the site repo so the trend survives
between sessions and between machines, and prints a summary.

Modules that need a key or a paid call are skipped with a stated reason rather
than failing the run. A missing PageSpeed key should never stop a crawl.
"""

from __future__ import annotations

import json
import sys

import findings as F
import history
import score as score_module


def _load(block: list[dict]) -> list[F.Finding]:
    return F.loads(json.dumps(block))


def run(cfg, *, live: bool = False, max_pages: int = 500, skip_perf: bool = False) -> dict:
    import ai_matrix
    import crawl
    import schema_check

    collected: list[F.Finding] = []
    stats: dict = {}
    notes: list[str] = []
    skipped: list[str] = []

    crawl_result = crawl.run(cfg, live=live, max_pages=max_pages)
    collected.extend(_load(crawl_result["findings"]))
    stats.update(crawl_result["stats"])
    notes.extend(crawl_result.get("notes", []))

    schema_result = schema_check.run(cfg, live=live, max_pages=max_pages)
    collected.extend(_load(schema_result["findings"]))
    stats["schema_pages_checked"] = schema_result["pages_checked"]
    stats["schema_types"] = len(schema_result["types_found"])

    ai_result = ai_matrix.run(cfg, live=live, skip_fetch=False)
    collected.extend(_load(ai_result["findings"]))
    stats["crawlers_evaluated"] = len(ai_result["bots"])
    notes.extend(ai_result.get("notes", []))

    perf_result: dict | None = None
    if skip_perf:
        skipped.append("module D (performance): skipped by request")
    else:
        import perf

        perf_result = perf.run(cfg)
        if perf_result.get("available"):
            collected.extend(_load(perf_result["findings"]))
            stats["templates_measured"] = len(perf_result.get("templates", []))
        else:
            skipped.append(f"module D (performance): {perf_result.get('reason')}")

    merged = F.order(F.merge(collected))
    finding_dicts = [f.to_dict() for f in merged]

    js_dependent = len(
        {
            url
            for f in finding_dicts
            if f["id"] == "ai.content_requires_javascript"
            for url in f["urls"]
        }
    )
    scores = score_module.both(
        finding_dicts,
        urls_checked=stats.get("pages_200", 0) or stats.get("pages_crawled", 0),
        bots=ai_result["bots"],
        js_dependent_pages=js_dependent,
        pages_checked=stats.get("pages_200", 0) or 1,
    )

    return {
        "kind": "audit",
        "site": cfg.site,
        "source": crawl_result["source"],
        "source_kind": crawl_result["source_kind"],
        "modules": ["A", "B", "C", "D", "E", "G"],
        "stats": stats,
        "scores": scores,
        "counts": F.counts(merged),
        "findings": finding_dicts,
        "bots": ai_result["bots"],
        "performance": perf_result if (perf_result or {}).get("available") else None,
        "skipped": skipped,
        "notes": notes,
    }


def render(result: dict, prior: dict | None = None) -> str:
    counts = result["counts"]
    lines = [
        f"siteseo audit: {result['site']}",
        f"  source  {result['source']} ({result['source_kind']})",
        f"  pages   {result['stats'].get('pages_crawled', 0)} crawled, "
        f"{result['stats'].get('pages_200', 0)} returned 200",
        "",
        "Scores",
        score_module.render(result["scores"], (prior or {}).get("scores")),
        "",
        f"Findings: {counts.get('error', 0)} errors, {counts.get('warning', 0)} warnings, "
        f"{counts.get('notice', 0)} notices",
        "",
    ]

    for severity in ("error", "warning"):
        band = [f for f in result["findings"] if f["severity"] == severity]
        if not band:
            continue
        lines.append(f"{severity.title()}s")
        for finding in band:
            urls = finding["urls"]
            where = urls[0] if len(urls) == 1 else f"{len(urls)} URLs"
            marker = " [autofix]" if finding.get("autofix") else ""
            lines.append(f"  {finding['id']:38s} {where}{marker}")
            lines.append(f"      {finding['evidence'][:150]}")
        lines.append("")

    notices = [f for f in result["findings"] if f["severity"] == "notice"]
    if notices:
        lines.append(f"Notices ({len(notices)}): " + ", ".join(sorted({f['id'] for f in notices})))
        lines.append("")

    for item in result.get("skipped", []):
        lines.append(f"Skipped: {item}")
    for note in result.get("notes", []):
        lines.append(f"Note: {note}")
    return "\n".join(lines)


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Full audit across modules A to E and G")
    parser.add_argument("--live", action="store_true", help="audit the deployed site over HTTP")
    parser.add_argument("--max-pages", type=int, default=500)
    parser.add_argument("--skip-perf", action="store_true")
    parser.add_argument("--no-snapshot", action="store_true", help="do not write to history")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    prior = history.latest(cfg, "audit")
    result = run(cfg, live=args.live, max_pages=args.max_pages, skip_perf=args.skip_perf)

    if not args.no_snapshot:
        path = history.write(cfg, "audit", result)
        result["snapshot"] = str(path)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render(result, prior))
        if not args.no_snapshot:
            print(f"\nSnapshot: {result['snapshot']}")
            print("Commit .siteseo/ so the trend travels with the repo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

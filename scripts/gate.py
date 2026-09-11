"""Pre-deploy gate. Free, offline, and fast enough for a pre-push hook.

Runs modules A, B, C and E against build output, exits 1 on any error-severity
finding, and prints a short summary. It makes no model call and no paid API
call, and that is enforced rather than promised: the process sets
SITESEO_OFFLINE, and the network source refuses to be constructed while it is
set. tests/test_gate_offline.py asserts the refusal actually fires.

Wire it in:

    # .git/hooks/pre-push
    npm run build && siteseo run gate.py || exit 1

    # GitHub Actions
    - run: npm run build
    - run: "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run gate.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import contextmanager

MODULES = ("A", "B", "C", "E")


@contextmanager
def offline():
    """Refuse network access for the duration, then restore what was there.

    Setting the flag and leaving it set would make every later call in the same
    process silently offline, which is a worse bug than the one this prevents.
    """
    previous = os.environ.get("SITESEO_OFFLINE")
    os.environ["SITESEO_OFFLINE"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SITESEO_OFFLINE", None)
        else:
            os.environ["SITESEO_OFFLINE"] = previous


def run(cfg, *, max_pages: int = 500) -> dict:
    import ai_matrix
    import crawl
    import findings as F
    import schema_check

    started = time.perf_counter()
    collected: list[F.Finding] = []
    stats: dict = {}

    with offline():
        crawl_result = crawl.run(cfg, live=False, max_pages=max_pages)
        collected.extend(F.loads(json.dumps(crawl_result["findings"])))
        stats.update(crawl_result["stats"])

        schema_result = schema_check.run(cfg, live=False, max_pages=max_pages)
        collected.extend(F.loads(json.dumps(schema_result["findings"])))
        stats["schema_pages_checked"] = schema_result["pages_checked"]

        ai_result = ai_matrix.run(cfg, live=False, skip_fetch=True)
        collected.extend(F.loads(json.dumps(ai_result["findings"])))
        stats["crawlers_evaluated"] = len(ai_result["bots"])

    # Modules A-D minus D, plus E. Module D needs PageSpeed, which costs a
    # key and a network round trip, so it never runs in the gate.
    kept = [f for f in collected if f.module in MODULES]
    ordered = F.order(F.merge(kept))
    counts = F.counts(ordered)

    return {
        "modules": list(MODULES),
        "site": cfg.site,
        "source": crawl_result["source"],
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "stats": stats,
        "counts": counts,
        "findings": [f.to_dict() for f in ordered],
        "passed": counts.get("error", 0) == 0,
        "notes": crawl_result.get("notes", []) + ai_result.get("notes", []),
    }


def render(result: dict) -> str:
    counts = result["counts"]
    lines = [
        f"siteseo gate: {result['site']}",
        f"  source   {result['source']}",
        f"  modules  {', '.join(result['modules'])} (no model calls, no paid APIs)",
        f"  pages    {result['stats'].get('pages_crawled', 0)} crawled "
        f"in {result['elapsed_seconds']}s",
        "",
    ]

    errors = [f for f in result["findings"] if f["severity"] == "error"]
    if errors:
        lines.append(f"{len(errors)} error(s) block this deploy:")
        lines.append("")
        for finding in errors:
            urls = finding["urls"]
            where = urls[0] if len(urls) == 1 else f"{len(urls)} URLs"
            lines.append(f"  {finding['id']}")
            lines.append(f"    {finding['evidence'][:160]}")
            lines.append(f"    {where}")
            lines.append(f"    fix: {finding['fix']}")
            lines.append("")
    else:
        lines.append("No errors.")
        lines.append("")

    lines.append(
        f"{counts.get('error', 0)} errors, {counts.get('warning', 0)} warnings, "
        f"{counts.get('notice', 0)} notices. Warnings and notices do not block."
    )
    lines.append("")
    lines.append("PASS" if result["passed"] else "FAIL")
    return "\n".join(lines)


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(
        description="Pre-deploy gate: modules A, B, C and E against build output"
    )
    parser.add_argument("--max-pages", type=int, default=500)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--warnings-fail",
        action="store_true",
        help="also exit 1 on warnings, for a stricter pipeline",
    )
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not cfg.build_path or not cfg.build_path.is_dir():
        print(
            f"The gate needs build output. `build_dir` in siteseo.yaml points at "
            f"{cfg.build_path}, which does not exist.\nBuild the site first.",
            file=sys.stderr,
        )
        return 2

    result = run(cfg, max_pages=args.max_pages)
    print(json.dumps(result, indent=2) if args.json else render(result))

    if not result["passed"]:
        return 1
    if args.warnings_fail and result["counts"].get("warning", 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

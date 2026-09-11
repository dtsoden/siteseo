"""Module K: bot hits and AI referrals from host or CDN logs.

This is the only check that confirms whether a crawler really reached the site.
The module E fetch test sends a crawler's user-agent string and reads the reply,
which proves that robots rules and user-agent filtering did not block it. It
cannot prove the real crawler gets through, because some operators verify
crawler IP ranges. Logs can.

Reads common access log formats from a directory you point it at. Static hosts
differ in what they expose, so this reports what it found rather than assuming a
format exists.
"""

from __future__ import annotations

import csv
import gzip
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import yaml

import findings as F

# Combined and common log format, which most hosts and CDNs still emit.
COMBINED = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] '
    r'"(?P<method>[A-Z]+) (?P<path>\S+) [^"]*" '
    r'(?P<status>\d{3}) (?P<bytes>\S+)'
    r'(?: "(?P<referer>[^"]*)" "(?P<agent>[^"]*)")?'
)

AI_REFERRERS = {
    "chatgpt.com": "ChatGPT",
    "chat.openai.com": "ChatGPT",
    "perplexity.ai": "Perplexity",
    "claude.ai": "Claude",
    "gemini.google.com": "Gemini",
    "copilot.microsoft.com": "Copilot",
    "bing.com/chat": "Copilot",
    "you.com": "You.com",
}

REFUSED = {401, 403, 429}


def _bot_tokens() -> dict[str, str]:
    path = F.plugin_root() / "skills" / "siteseo" / "reference" / "ai-bots.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {entry["token"].lower(): entry["token"] for entry in raw.get("bots", [])}


def _open(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("r", encoding="utf-8", errors="replace")


def _parse_line(line: str) -> dict | None:
    match = COMBINED.match(line)
    if match:
        return match.groupdict()
    return None


def _parse_csv_row(row: dict) -> dict | None:
    """Cloudflare and similar CDN exports, which ship CSV rather than combined."""
    agent = row.get("ClientRequestUserAgent") or row.get("user_agent") or row.get("UserAgent")
    status = row.get("EdgeResponseStatus") or row.get("status") or row.get("Status")
    if agent is None or status is None:
        return None
    return {
        "agent": agent,
        "status": status,
        "path": row.get("ClientRequestURI") or row.get("path") or "",
        "time": row.get("EdgeStartTimestamp") or row.get("date") or "",
        "referer": row.get("ClientRequestReferer") or row.get("referer") or "",
    }


def scan(folder: Path) -> dict:
    tokens = _bot_tokens()
    hits: dict[str, dict] = defaultdict(
        lambda: {"total": 0, "statuses": defaultdict(int), "days": defaultdict(int), "paths": defaultdict(int)}
    )
    referrals: dict[str, int] = defaultdict(int)
    lines_read = 0
    files_read: list[str] = []

    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix not in {".log", ".txt", ".gz", ".csv"}:
            continue
        files_read.append(path.name)

        if path.suffix == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    lines_read += 1
                    parsed = _parse_csv_row(row)
                    if parsed:
                        _record(parsed, tokens, hits, referrals)
            continue

        with _open(path) as handle:
            for line in handle:
                lines_read += 1
                parsed = _parse_line(line)
                if parsed:
                    _record(parsed, tokens, hits, referrals)

    return {
        "folder": str(folder),
        "files_read": files_read,
        "lines_read": lines_read,
        "bots": {
            token: {
                "total": data["total"],
                "statuses": dict(sorted(data["statuses"].items())),
                "days": len(data["days"]),
                "top_paths": dict(sorted(data["paths"].items(), key=lambda kv: -kv[1])[:5]),
            }
            for token, data in sorted(hits.items())
        },
        "ai_referrals": dict(sorted(referrals.items(), key=lambda kv: -kv[1])),
    }


def _record(parsed: dict, tokens: dict[str, str], hits: dict, referrals: dict) -> None:
    agent = (parsed.get("agent") or "").lower()
    for token_lower, token in tokens.items():
        if token_lower in agent:
            entry = hits[token]
            entry["total"] += 1
            try:
                entry["statuses"][int(parsed["status"])] += 1
            except (TypeError, ValueError):
                pass
            entry["days"][str(parsed.get("time", ""))[:11]] += 1
            entry["paths"][parsed.get("path", "")] += 1
            break

    referer = (parsed.get("referer") or "").lower()
    for host, label in AI_REFERRERS.items():
        if host in referer:
            referrals[label] += 1
            break


def run(cfg, folder: Path | None = None) -> dict:
    folder = folder or (cfg.imports_dir / "logs")
    if not folder.is_dir():
        return {
            "module": "K",
            "source": "logs",
            "available": False,
            "reason": (
                f"no log directory at {folder}. Export access logs from your host or CDN "
                "and drop them there. Static hosts differ in what they expose, so siteseo "
                "reads what is present rather than assuming a format."
            ),
            "findings": [],
        }

    result = scan(folder)
    emitted: list[F.Finding] = []

    for token, data in result["bots"].items():
        refused = sum(count for status, count in data["statuses"].items() if status in REFUSED)
        if refused and refused / max(data["total"], 1) > 0.2:
            emitted.append(
                F.make(
                    "ai_vis.bot_blocked_in_logs",
                    cfg.site,
                    f"{token} was refused on {refused} of {data['total']} requests "
                    f"(statuses {dict(data['statuses'])}). User-agent rules alone do not "
                    "explain this, so check CDN bot rules and rate limits.",
                    group=token,
                )
            )

    if not result["ai_referrals"]:
        emitted.append(
            F.make(
                "ai_vis.no_referrals",
                cfg.site,
                f"no referrals from AI assistants across {result['lines_read']} log lines",
            )
        )

    result.update(
        {
            "module": "K",
            "source": "logs",
            "available": True,
            "site": cfg.site,
            "findings": [f.to_dict() for f in F.order(F.merge(emitted))],
            "notes": [
                "Bot hits are the only evidence that a crawler actually reached the site. "
                "A module E fetch test can only show that user-agent rules did not block it."
            ],
        }
    )
    return result


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Module K: bot hits and AI referrals from logs")
    parser.add_argument("--folder", help="directory of access logs")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = run(cfg, Path(args.folder) if args.folder else None)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    if not result["available"]:
        print(f"Log analysis unavailable: {result['reason']}")
        return 0

    print(f"Read {result['lines_read']} lines from {len(result['files_read'])} file(s)")
    print()
    if result["bots"]:
        print(f"{'crawler':22s} {'hits':>7s} {'days':>5s}  statuses")
        for token, data in result["bots"].items():
            print(f"{token:22s} {data['total']:7d} {data['days']:5d}  {dict(data['statuses'])}")
    else:
        print("No AI crawler hits found in these logs.")
    print()
    if result["ai_referrals"]:
        print("AI referrals:")
        for label, count in result["ai_referrals"].items():
            print(f"  {label:14s} {count}")
    else:
        print("No AI assistant referrals found.")
    print()
    for finding in result["findings"]:
        print(f"  [{finding['severity']}] {finding['id']}: {finding['evidence'][:150]}")
    for note in result.get("notes", []):
        print(f"\nNote: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


_ = datetime

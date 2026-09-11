"""Dated snapshots committed to the site repo.

History lives with the site, not in a cache directory on one machine. Clone the
repo somewhere else and the trend is already there. That is the whole reason
this is a file in the repo rather than a database in a home directory.

File name is `YYYY-MM-DD-HHMMSS-<kind>.json`, so snapshots sort lexically and a
second run on the same day never overwrites the first.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STAMP = "%Y-%m-%d-%H%M%S"


def _now() -> str:
    return datetime.now(timezone.utc).strftime(STAMP)


def write(cfg, kind: str, payload: dict[str, Any]) -> Path:
    """Save a snapshot. Returns the path written.

    Stamps the caller's dict as well as the saved copy, so callers can name
    their own artefacts with the same timestamp the snapshot carries.
    """
    cfg.ensure_dir(cfg.history_dir)
    payload.setdefault("recorded_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    payload.setdefault("kind", kind)
    payload.setdefault("site", cfg.site)
    payload = dict(payload)

    path = cfg.history_dir / f"{_now()}-{kind}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    return path


def snapshots(cfg, kind: str | None = None) -> list[Path]:
    """Every snapshot, oldest first."""
    if not cfg.history_dir.is_dir():
        return []
    suffix = f"-{kind}.json" if kind else ".json"
    return sorted(p for p in cfg.history_dir.glob("*.json") if p.name.endswith(suffix))


def latest(cfg, kind: str | None = None) -> dict | None:
    found = snapshots(cfg, kind)
    if not found:
        return None
    return json.loads(found[-1].read_text(encoding="utf-8"))


def previous(cfg, kind: str | None = None) -> dict | None:
    """The snapshot before the most recent one, for diffing."""
    found = snapshots(cfg, kind)
    if len(found) < 2:
        return None
    return json.loads(found[-2].read_text(encoding="utf-8"))


def diff_findings(current: list[dict], prior: list[dict]) -> dict[str, list[dict]]:
    """What changed between two finding sets, keyed by id plus group."""

    def key(finding: dict) -> tuple[str, str]:
        return finding["id"], finding.get("group", "")

    now = {key(f): f for f in current}
    before = {key(f): f for f in prior}

    return {
        "new": [now[k] for k in now.keys() - before.keys()],
        "resolved": [before[k] for k in before.keys() - now.keys()],
        "unchanged": [now[k] for k in now.keys() & before.keys()],
    }


def prune(cfg, keep: int = 60, kind: str | None = None) -> list[Path]:
    """Drop the oldest snapshots past `keep`. Returns what was removed."""
    found = snapshots(cfg, kind)
    removed = found[:-keep] if len(found) > keep else []
    for path in removed:
        path.unlink()
    return removed

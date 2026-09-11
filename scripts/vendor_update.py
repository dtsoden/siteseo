"""Refresh vendored files to upstream head and rewrite the pins.

Only the weekly workflow runs this, and only into a pull request branch. Nothing
it writes reaches a machine until a human reads the diff and merges. Running it
locally is fine, but the same rule applies: read the diff.

It refuses to change which files are vendored. The set of vendored paths is a
decision made by a person editing upstream.lock, not something a scheduled job
gets to widen.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path


def plugin_root() -> Path:
    import os

    return Path(os.environ.get("SITESEO_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _local_path(root: Path, repo: str, relative: str) -> Path:
    name = Path(relative).name if relative == "LICENSE" else relative
    return root / "vendor" / repo.split("/")[-1] / name


def run(root: Path) -> dict:
    lock_path = root / "upstream.lock"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    changed: list[str] = []

    for source in lock.get("sources", []):
        repo, url = source["repo"], source["url"]
        with tempfile.TemporaryDirectory() as workspace:
            clone = Path(workspace) / "clone"
            subprocess.run(
                ["git", "clone", "--depth", "1", "--quiet", url, str(clone)],
                check=True, capture_output=True, text=True,
            )
            head = subprocess.run(
                ["git", "-C", str(clone), "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()

            for relative in list(source.get("files") or {}):
                upstream_file = clone / relative
                if not upstream_file.is_file():
                    # A vendored file disappearing upstream is a decision for a
                    # person, not something to resolve by deleting it here.
                    changed.append(f"{repo}:{relative} no longer exists upstream, left in place")
                    continue

                target = _local_path(root, repo, relative)
                new_hash = _sha256(upstream_file)
                if source["files"][relative] == new_hash:
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(upstream_file, target)
                source["files"][relative] = new_hash
                changed.append(f"{repo}:{relative} updated")

            if head != source.get("commit"):
                changed.append(f"{repo} pin moved {source['commit'][:12]} to {head[:12]}")
                source["commit"] = head
            source["pinned_at"] = date.today().isoformat()

    lock["generated"] = date.today().isoformat()
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return {"changed": changed, "lock": str(lock_path)}


def main() -> int:
    root = plugin_root()
    try:
        result = run(root)
    except subprocess.CalledProcessError as exc:
        print(f"clone failed: {exc.stderr.strip()[:300]}", file=sys.stderr)
        return 2

    if not result["changed"]:
        print("Nothing to update. Every vendored file already matches upstream.")
        return 0

    print(f"Updated {result['lock']}:")
    for line in result["changed"]:
        print(f"  {line}")
    print("\nRead the diff before merging. Nothing reaches a machine until this lands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

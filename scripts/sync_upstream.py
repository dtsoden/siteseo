"""Check both drift clocks and report what moved.

Code drift: every vendored file is pinned in upstream.lock by commit and content
hash. This refetches each upstream at its head, compares, and prints a diff. It
never writes a vendored file on its own. The weekly workflow runs it and opens a
pull request, so a human reads the diff before anything reaches a machine.

Knowledge drift: the reference files carry last_verified dates. Crawler names and
rich result rules change without any repository moving, so a file past ninety
days is reported even when no code changed.

Exit codes: 0 nothing moved, 1 drift found, 2 the check itself failed.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

STALE_AFTER_DAYS = 90
LAST_VERIFIED = re.compile(r"^\s*(?:#\s*)?last_verified:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", re.M)


def plugin_root() -> Path:
    import os

    return Path(os.environ.get("SITESEO_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent)


@dataclass
class Drift:
    repo: str
    kind: str
    detail: str
    diff: str = ""


@dataclass
class Report:
    code_drift: list[Drift] = field(default_factory=list)
    stale_reference: list[Drift] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    checked_files: int = 0

    @property
    def clean(self) -> bool:
        return not self.code_drift and not self.stale_reference and not self.errors


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _clone(url: str, into: Path) -> str:
    # core.autocrlf=false so the comparison is against upstream's real bytes.
    subprocess.run(
        ["git", "-c", "core.autocrlf=false", "clone",
         "--depth", "1", "--quiet", url, str(into)],
        check=True, capture_output=True, text=True,
    )
    return subprocess.run(
        ["git", "-C", str(into), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def check_code(root: Path, report: Report) -> None:
    lock_path = root / "upstream.lock"
    if not lock_path.is_file():
        report.errors.append("upstream.lock is missing")
        return

    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report.errors.append(f"upstream.lock is not valid JSON: {exc}")
        return

    for source in lock.get("sources", []):
        repo = source["repo"]
        with tempfile.TemporaryDirectory() as workspace:
            clone_dir = Path(workspace) / "clone"
            try:
                head = _clone(source["url"], clone_dir)
            except subprocess.CalledProcessError as exc:
                report.errors.append(f"{repo}: clone failed: {exc.stderr.strip()[:200]}")
                continue

            if head != source.get("commit"):
                report.code_drift.append(
                    Drift(
                        repo,
                        "commit",
                        f"pinned at {source['commit'][:12]}, upstream head is {head[:12]}",
                    )
                )

            for relative, pinned_hash in (source.get("files") or {}).items():
                report.checked_files += 1
                upstream_file = clone_dir / relative
                local_name = Path(relative).name if relative == "LICENSE" else relative
                local_file = root / "vendor" / repo.split("/")[-1] / local_name

                if not local_file.is_file():
                    report.errors.append(f"{repo}:{relative} is missing from vendor/")
                    continue

                local_bytes = local_file.read_bytes()
                if _sha256(local_bytes) != pinned_hash:
                    report.code_drift.append(
                        Drift(
                            repo,
                            "local",
                            f"{relative} does not match its pinned hash. The vendored copy "
                            "was edited locally, which the lockfile does not allow.",
                        )
                    )

                if not upstream_file.is_file():
                    report.code_drift.append(
                        Drift(repo, "removed", f"{relative} no longer exists upstream")
                    )
                    continue

                upstream_bytes = upstream_file.read_bytes()
                if _sha256(upstream_bytes) != pinned_hash:
                    diff = "".join(
                        difflib.unified_diff(
                            local_bytes.decode("utf-8", "replace").splitlines(keepends=True),
                            upstream_bytes.decode("utf-8", "replace").splitlines(keepends=True),
                            fromfile=f"pinned/{relative}",
                            tofile=f"upstream/{relative}",
                            n=2,
                        )
                    )
                    report.code_drift.append(
                        Drift(repo, "content", f"{relative} changed upstream", diff)
                    )


SCANNER = "isitagentready.com"
PINNED_SKILL = re.compile(r"^    ([a-z0-9-]+): (sha256:[0-9a-f]{64})[ \t]*$", re.M)


def _agent_reference(root: Path) -> Path:
    return root / "skills" / "siteseo" / "reference" / "agent-readiness.yaml"


def _fetch_json(url: str) -> dict:
    import urllib.request

    # Cloudflare refuses Python's default user agent, so name this tool instead.
    request = urllib.request.Request(url, headers={"User-Agent": "siteseo-sync (+https://github.com/dtsoden/siteseo)"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _published_skills(root: Path, fetch) -> tuple[dict[str, str], dict[str, str]]:
    import yaml

    reference = yaml.safe_load(_agent_reference(root).read_text(encoding="utf-8")) or {}
    scanner = reference.get("scanner") or {}
    index = fetch(scanner["skills_index"])
    published = {
        entry["name"]: entry.get("digest", "")
        for entry in index.get("skills", [])
        if isinstance(entry, dict) and entry.get("name")
    }
    return scanner.get("skills") or {}, published


def check_agent_scanner(root: Path, report: Report, fetch=_fetch_json) -> None:
    """Report any change to the skills Cloudflare's agent readiness scanner publishes.

    The scanner's source is not public. Each check it runs ships a SKILL.md with a
    digest in its discovery index, so a changed digest is the earliest public sign
    that a check's criteria moved, and a new name is a check that did not exist.
    """
    try:
        pinned, published = _published_skills(root, fetch)
    except Exception as exc:  # network, JSON, or a reshaped index
        report.errors.append(f"{SCANNER} skills index: {type(exc).__name__}: {exc}")
        return

    for name in sorted(published.keys() - pinned.keys()):
        report.code_drift.append(Drift(
            SCANNER, "added",
            f"new skill {name}: the scanner probably checks something new; "
            "consider a module O check and a row in agent-readiness.md",
        ))
    for name in sorted(pinned.keys() - published.keys()):
        report.code_drift.append(Drift(
            SCANNER, "removed", f"skill {name} is gone: the scanner may have dropped that check",
        ))
    for name in sorted(pinned.keys() & published.keys()):
        if pinned[name] != published[name]:
            report.code_drift.append(Drift(
                SCANNER, "content",
                f"skill {name} changed: re-read its SKILL.md against the matching module O check",
            ))


def update_scanner_pins(root: Path, fetch=_fetch_json) -> bool:
    """Rewrite the pinned digests to match what the scanner publishes now.

    Only the digest lines change, so the pull request diff shows exactly which
    skills moved. Returns True when the file changed.
    """
    _, published = _published_skills(root, fetch)
    path = _agent_reference(root)
    text = path.read_text(encoding="utf-8")
    matches = list(PINNED_SKILL.finditer(text))
    if not matches:
        raise ValueError(f"no pinned skill digests found in {path.name}")
    block = "".join(f"    {name}: {digest}\n" for name, digest in published.items())
    start, end = matches[0].start(), matches[-1].end()
    if end < len(text) and text[end] == "\n":
        end += 1
    updated = text[:start] + block + text[end:]
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def check_reference(root: Path, report: Report) -> None:
    reference = root / "skills" / "siteseo" / "reference"
    if not reference.is_dir():
        report.errors.append(f"reference directory missing at {reference}")
        return

    today = date.today()
    for path in sorted(reference.iterdir()):
        if path.suffix not in {".yaml", ".yml", ".md"} or not path.is_file():
            continue
        match = LAST_VERIFIED.search(path.read_text(encoding="utf-8", errors="replace"))
        if not match:
            report.stale_reference.append(
                Drift("reference", "undated", f"{path.name} carries no last_verified date")
            )
            continue
        age = (today - date.fromisoformat(match.group(1))).days
        if age > STALE_AFTER_DAYS:
            report.stale_reference.append(
                Drift(
                    "reference",
                    "stale",
                    f"{path.name} was last verified {match.group(1)}, {age} days ago. "
                    "Crawler names and rich result rules change without any repository "
                    "moving, so re-check it against its source.",
                )
            )


def render(report: Report) -> str:
    lines = ["siteseo upstream sync", ""]

    lines.append(f"Code drift ({report.checked_files} vendored files checked)")
    if not report.code_drift:
        lines.append("  nothing moved")
    for drift in report.code_drift:
        lines.append(f"  [{drift.kind}] {drift.repo}: {drift.detail}")
        if drift.diff:
            lines.extend("      " + line.rstrip("\n") for line in drift.diff.splitlines()[:40])
    lines.append("")

    lines.append(f"Reference freshness (stale after {STALE_AFTER_DAYS} days)")
    if not report.stale_reference:
        lines.append("  everything current")
    for drift in report.stale_reference:
        lines.append(f"  [{drift.kind}] {drift.detail}")
    lines.append("")

    if report.errors:
        lines.append("Errors")
        for error in report.errors:
            lines.append(f"  {error}")
        lines.append("")

    lines.append("Clean." if report.clean else "Drift found. Review before updating the pins.")
    return "\n".join(lines)


def markdown_summary(report: Report) -> str:
    """Body for the weekly pull request."""
    lines = ["## Upstream drift", ""]
    if report.code_drift:
        for drift in report.code_drift:
            lines.append(f"- **{drift.repo}** ({drift.kind}): {drift.detail}")
    else:
        lines.append("- No vendored file moved.")
    lines.append("")
    lines.append("## Reference freshness")
    lines.append("")
    if report.stale_reference:
        for drift in report.stale_reference:
            lines.append(f"- {drift.detail}")
    else:
        lines.append("- Every reference file is within 90 days.")
    lines.append("")
    lines.append(
        "Read the diff before merging. Vendored code is not executed until this "
        "pull request lands and machines pick it up on their next plugin update."
    )
    return "\n".join(lines)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Check upstream and reference drift")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--markdown", action="store_true", help="pull request body")
    parser.add_argument("--reference-only", action="store_true", help="skip network clones")
    parser.add_argument(
        "--update-scanner-pins", action="store_true",
        help="rewrite the agent readiness scanner digests to what it publishes now",
    )
    args = parser.parse_args()

    root = plugin_root()

    if args.update_scanner_pins:
        changed = update_scanner_pins(root)
        print("scanner pins updated" if changed else "scanner pins already current")
        return 0

    report = Report()

    if not args.reference_only:
        check_code(root, report)
        check_agent_scanner(root, report)
    check_reference(root, report)

    if args.json:
        print(json.dumps(
            {
                "clean": report.clean,
                "checked_files": report.checked_files,
                "code_drift": [vars(d) for d in report.code_drift],
                "stale_reference": [vars(d) for d in report.stale_reference],
                "errors": report.errors,
            },
            indent=2,
        ))
    elif args.markdown:
        print(markdown_summary(report))
    else:
        print(render(report))

    if report.errors:
        return 2
    return 0 if report.clean else 1


if __name__ == "__main__":
    raise SystemExit(main())

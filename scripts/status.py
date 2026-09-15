"""Where this repository stands with siteseo, for the guided `/siteseo` flow.

Runs under the bootstrap interpreter with the standard library only, because its
first job is to say whether setup has happened at all. It never reads a secret
and never makes a network request.

    siteseo status [--json]

`next_step` is one of:

    setup         the isolated Python environment is not built on this machine
    init          no siteseo.yaml in this repository
    build         siteseo.yaml names a build_dir that does not exist yet
    first_report  configured, but no audit has ever been run here
    ready         at least one audit exists
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import runtime  # noqa: E402

CONFIG_NAME = "siteseo.yaml"
BUILD_CANDIDATES = ("dist", "build", "out", "_site", "public", "site", "docs")
STACK_MARKERS = {
    "astro": ("astro.config.mjs", "astro.config.ts", "astro.config.js"),
    "next": ("next.config.js", "next.config.mjs", "next.config.ts"),
    "hugo": ("hugo.toml", "hugo.yaml", "config.toml"),
    "eleventy": (".eleventy.js", "eleventy.config.js", "eleventy.config.mjs"),
}
HOST_MARKERS = {
    "cloudflare-pages": ("wrangler.toml", "wrangler.jsonc", "wrangler.json"),
    "netlify": ("netlify.toml",),
    "vercel": ("vercel.json",),
}
MARKDOWN_MARKER = "generator: siteseo"


def _repo_root(start: Path) -> Path:
    for directory in (start, *start.parents):
        if (directory / ".git").exists():
            return directory
    return start


def _find_config(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def _scalar(text: str, key: str, indent: str = "") -> str | None:
    """A top-level or singly nested scalar, read without a YAML parser."""
    match = re.search(rf"^{indent}{re.escape(key)}:\s*([^#\n]*?)\s*(?:#.*)?$", text, re.M)
    if not match or not match.group(1):
        return None
    return match.group(1).strip().strip("'\"")


def _detect(root: Path) -> dict:
    stack = next((name for name, files in STACK_MARKERS.items()
                  if any((root / f).is_file() for f in files)), None)
    host = next((name for name, files in HOST_MARKERS.items()
                 if any((root / f).is_file() for f in files)), None)
    if host is None and (root / "CNAME").is_file():
        host = "github-pages"
    builds = [name for name in BUILD_CANDIDATES
              if (root / name).is_dir() and any((root / name).rglob("*.html"))]
    return {"stack": stack, "host": host, "build_dirs": builds}


def _latest_audit(root: Path) -> tuple[int, dict | None]:
    history = root / ".siteseo" / "history"
    audits = sorted(history.glob("*-audit.json")) if history.is_dir() else []
    if not audits:
        return 0, None
    try:
        data = json.loads(audits[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return len(audits), {"file": audits[-1].name, "unreadable": True}
    scores = data.get("scores") or {}
    agent = data.get("agent_readiness") or {}
    reports = root / ".siteseo" / "reports"
    report = sorted(reports.glob("*-audit.md"))[-1].name if reports.is_dir() and any(
        reports.glob("*-audit.md")) else None
    return len(audits), {
        "file": audits[-1].name,
        "recorded_at": data.get("recorded_at"),
        "source_kind": data.get("source_kind"),
        "search_health": (scores.get("search_health") or {}).get("value"),
        "ai_access": (scores.get("ai_access") or {}).get("value"),
        "agent_level": agent.get("level"),
        "agent_level_name": agent.get("level_name"),
        "counts": data.get("counts"),
        "report": f".siteseo/reports/{report}" if report else None,
    }


def state(start: Path | None = None) -> dict:
    cwd = (start or Path.cwd()).resolve()
    config_path = _find_config(cwd)
    root = config_path.parent if config_path else _repo_root(cwd)

    config = None
    if config_path:
        text = config_path.read_text(encoding="utf-8", errors="replace")
        build_dir = _scalar(text, "build_dir")
        config = {
            "path": str(config_path),
            "site": _scalar(text, "site"),
            "build_dir": build_dir,
            "build_dir_exists": bool(build_dir) and (root / build_dir).is_dir(),
            "host": _scalar(text, "host"),
            "profile": _scalar(text, "profile", "  "),
        }

    audits, latest = _latest_audit(root)
    markdown = 0
    if config and config["build_dir_exists"]:
        for path in (root / config["build_dir"]).rglob("*.md"):
            try:
                if MARKDOWN_MARKER in path.read_text(encoding="utf-8", errors="replace")[:2048]:
                    markdown += 1
            except OSError:
                continue

    if not runtime.is_ready():
        next_step = "setup"
    elif config is None:
        next_step = "init"
    elif config["build_dir"] and not config["build_dir_exists"]:
        next_step = "build"
    elif audits == 0:
        next_step = "first_report"
    else:
        next_step = "ready"

    return {
        "repo_root": str(root),
        "runtime_ready": runtime.is_ready(),
        "config": config,
        "detected": _detect(root),
        "audits": audits,
        "latest_audit": latest,
        "markdown_files": markdown,
        "next_step": next_step,
    }


def render(result: dict) -> str:
    lines = [f"siteseo status for {result['repo_root']}", ""]
    lines.append(f"  environment   {'ready' if result['runtime_ready'] else 'not set up'}")
    config = result["config"]
    if config:
        build = config["build_dir"] or "(none, live site only)"
        if config["build_dir"] and not config["build_dir_exists"]:
            build += " (does not exist yet)"
        lines.append(f"  config        {config['path']}")
        lines.append(f"  site          {config['site']}")
        lines.append(f"  build output  {build}")
    else:
        detected = result["detected"]
        lines.append("  config        none")
        lines.append(
            f"  detected      stack {detected['stack'] or 'unknown'}, host {detected['host'] or 'unknown'}, "
            f"build output {', '.join(detected['build_dirs']) or 'none found'}"
        )
    latest = result["latest_audit"]
    if latest and not latest.get("unreadable"):
        lines.append(
            f"  last report   {latest['recorded_at']}: search health {latest['search_health']}, "
            f"AI access {latest['ai_access']}, agent readiness level {latest['agent_level']}"
        )
    else:
        lines.append("  last report   never run")
    lines += ["", f"  next step     {result['next_step']}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    result = state()
    print(json.dumps(result, indent=2) if "--json" in argv else render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

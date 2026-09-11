"""Report what siteseo can and cannot do on THIS machine.

Runs under the bootstrap interpreter using only the standard library, because
one of the things it has to be able to report is that the isolated environment
does not exist yet.

Never prints a secret value. Secret names only.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import runtime  # noqa: E402

PLUGIN_ROOT = runtime.PLUGIN_ROOT
REFERENCE = PLUGIN_ROOT / "skills" / "siteseo" / "reference"
STALE_AFTER_DAYS = 90

# Name, what it unlocks. Values live in the OS vault, never here.
SECRETS = [
    ("SITESEO_GSC_SERVICE_ACCOUNT", "Search Console pulls and URL Inspection (module J)"),
    ("SITESEO_PAGESPEED_API_KEY", "PageSpeed Insights and CrUX (module D)"),
    ("SITESEO_BING_API_KEY", "Bing Webmaster query and crawl data (module J)"),
    ("SITESEO_DATAFORSEO_LOGIN", "Keyword, SERP and backlink research (modules L and M)"),
    ("SITESEO_DATAFORSEO_PASSWORD", "Keyword, SERP and backlink research (modules L and M)"),
    ("SITESEO_ANTHROPIC_API_KEY", "AI visibility tracking (module K)"),
    ("SITESEO_OPENAI_API_KEY", "AI visibility tracking (module K)"),
    ("SITESEO_PERPLEXITY_API_KEY", "AI visibility tracking (module K)"),
]

LAST_VERIFIED = re.compile(r"^\s*(?:#\s*)?last_verified:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", re.M)


def _env_has(name: str) -> bool:
    import os

    return bool(os.environ.get(name, "").strip())


def _aihsm_available() -> bool:
    return shutil.which("aihsm") is not None


def _aihsm_names() -> set[str]:
    """Ask the vault which names it holds. Names only, never values."""
    if not _aihsm_available():
        return set()
    for args in (["aihsm", "list", "--json"], ["aihsm", "list"]):
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=15)
        except Exception:
            continue
        if proc.returncode != 0:
            continue
        out = proc.stdout.strip()
        if not out:
            continue
        try:
            parsed = json.loads(out)
            if isinstance(parsed, list):
                return {str(x) for x in parsed}
            if isinstance(parsed, dict):
                return {str(k) for k in parsed}
        except json.JSONDecodeError:
            return {line.strip() for line in out.splitlines() if line.strip()}
    return set()


def check_runtime() -> dict:
    info: dict = {
        "bootstrap_python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": sys.platform,
        "uv": runtime.find_uv() is not None,
        "env_dir": str(runtime.env_dir()),
        "env_ready": runtime.is_ready(),
        "chromium": False,
    }
    if info["env_ready"]:
        info["chromium"] = runtime.chromium_ready()
    return info


def check_secrets() -> list[dict]:
    vault = _aihsm_names()
    rows = []
    for name, unlocks in SECRETS:
        source = None
        if _env_has(name):
            source = "environment"
        elif name in vault:
            source = "vault"
        rows.append({"name": name, "resolved": source is not None, "source": source, "unlocks": unlocks})
    return rows


def check_reference() -> list[dict]:
    rows = []
    if not REFERENCE.is_dir():
        return rows
    today = date.today()
    for path in sorted(REFERENCE.iterdir()):
        if path.suffix not in {".yaml", ".yml", ".md"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        match = LAST_VERIFIED.search(text)
        if not match:
            rows.append({"file": path.name, "last_verified": None, "age_days": None, "stale": False})
            continue
        verified = date.fromisoformat(match.group(1))
        age = (today - verified).days
        rows.append(
            {
                "file": path.name,
                "last_verified": match.group(1),
                "age_days": age,
                "stale": age > STALE_AFTER_DAYS,
            }
        )
    return rows


def check_upstream() -> list[dict]:
    lock = PLUGIN_ROOT / "upstream.lock"
    if not lock.is_file():
        return []
    try:
        data = json.loads(lock.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [{"source": "upstream.lock", "error": "not valid JSON"}]
    rows = []
    for source in data.get("sources", []):
        rows.append(
            {
                "source": source.get("repo"),
                "commit": (source.get("commit") or "")[:12],
                "pinned_at": source.get("pinned_at"),
                "files": len(source.get("files", {})),
            }
        )
    return rows


def build_report() -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "0.2.1",
        "plugin_root": str(PLUGIN_ROOT),
        "runtime": check_runtime(),
        "secrets": check_secrets(),
        "reference": check_reference(),
        "upstream": check_upstream(),
    }


def _mark(ok: bool) -> str:
    return "ok  " if ok else "MISS"


def render(report: dict) -> str:
    rt = report["runtime"]
    lines = ["siteseo doctor", ""]

    lines.append("Runtime")
    lines.append(f"  {_mark(True)} bootstrap Python {rt['bootstrap_python']} on {rt['platform']}")
    lines.append(f"  {_mark(rt['uv'])} uv {'found' if rt['uv'] else 'not found (venv plus pip will be used)'}")
    lines.append(f"  {_mark(rt['env_ready'])} isolated environment")
    lines.append(f"       {rt['env_dir']}")
    if not rt["env_ready"]:
        lines.append("       run: siteseo setup")
    lines.append(
        f"  {_mark(rt['chromium'])} Chromium"
        + ("" if rt["chromium"] else "  (module A rendered-DOM check will be skipped)")
    )
    if not rt["chromium"] and rt["env_ready"]:
        lines.append("       run: siteseo setup --chromium")

    lines.append("")
    lines.append("Secrets on this machine (names only, values are never read here)")
    for row in report["secrets"]:
        where = f" via {row['source']}" if row["source"] else ""
        lines.append(f"  {_mark(row['resolved'])} {row['name']}{where}")
        if not row["resolved"]:
            lines.append(f"       unlocks: {row['unlocks']}")

    lines.append("")
    lines.append("Reference data freshness")
    if not report["reference"]:
        lines.append("  no reference files found")
    for row in report["reference"]:
        if row["last_verified"] is None:
            lines.append(f"  ??   {row['file']}  no last_verified date")
        else:
            state = "STALE" if row["stale"] else "ok  "
            lines.append(
                f"  {state} {row['file']}  verified {row['last_verified']} "
                f"({row['age_days']} days ago)"
            )
    if any(r.get("stale") for r in report["reference"]):
        lines.append(f"       anything past {STALE_AFTER_DAYS} days needs re-checking against its source")

    lines.append("")
    lines.append("Vendored upstream pins")
    if not report["upstream"]:
        lines.append("  no upstream.lock found")
    for row in report["upstream"]:
        if "error" in row:
            lines.append(f"  ERR  {row['source']}: {row['error']}")
        else:
            lines.append(
                f"  ok   {row['source']} @ {row['commit']}  "
                f"{row['files']} files, pinned {row['pinned_at']}"
            )

    blocking = not rt["env_ready"]
    lines.append("")
    lines.append("Ready to audit." if not blocking else "Not ready. Run siteseo setup first.")
    return "\n".join(lines)


def main() -> int:
    as_json = "--json" in sys.argv[1:]
    report = build_report()
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report))
    return 0 if report["runtime"]["env_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

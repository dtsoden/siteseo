"""Read secrets by name, never write or print them.

Order of resolution:
  1. Process environment.
  2. The OS vault through the aihsm CLI.

A value read here must never reach stdout, a log, a history snapshot, or the
repository. `describe()` exists so callers can say what is missing without
saying what it is.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache

#: What each name unlocks, for messages that explain a skip.
PURPOSE = {
    "SITESEO_GSC_SERVICE_ACCOUNT": "Search Console pulls and URL Inspection (module J)",
    "SITESEO_PAGESPEED_API_KEY": "PageSpeed Insights and CrUX (module D)",
    "SITESEO_BING_API_KEY": "Bing Webmaster query and crawl data (module J)",
    "SITESEO_DATAFORSEO_LOGIN": "keyword, SERP and backlink research (modules L and M)",
    "SITESEO_DATAFORSEO_PASSWORD": "keyword, SERP and backlink research (modules L and M)",
    "SITESEO_ANTHROPIC_API_KEY": "AI visibility tracking (module K)",
    "SITESEO_OPENAI_API_KEY": "AI visibility tracking (module K)",
    "SITESEO_PERPLEXITY_API_KEY": "AI visibility tracking (module K)",
}


class MissingSecret(RuntimeError):
    """Raised when a required secret is not available on this machine."""


@lru_cache(maxsize=1)
def _vault_available() -> bool:
    return shutil.which("aihsm") is not None


def get(name: str) -> str | None:
    """The secret's value, or None. Never logs and never raises on absence."""
    value = os.environ.get(name)
    if value and value.strip():
        return value.strip()

    if not _vault_available():
        return None

    # aihsm injects into a child process rather than printing, so ask a tiny
    # child to echo it back on stdout and capture that. The value stays out of
    # the parent's argv and out of any log this process writes.
    try:
        proc = subprocess.run(
            [
                "aihsm", "run", "--set", f"SITESEO_SECRET={name}", "--",
                "python", "-c", "import os,sys; sys.stdout.write(os.environ.get('SITESEO_SECRET',''))",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def require(name: str) -> str:
    value = get(name)
    if not value:
        raise MissingSecret(
            f"{name} is not set on this machine. It unlocks "
            f"{PURPOSE.get(name, 'a paid or authenticated feature')}.\n"
            f"Store it in your OS vault, or export it for this shell. "
            f"Run `siteseo doctor` to see what else is missing."
        )
    return value


def available(name: str) -> bool:
    return get(name) is not None


def describe(name: str) -> str:
    """A message safe to print: says whether it resolves, never what it is."""
    state = "available" if available(name) else "not set"
    return f"{name}: {state} ({PURPOSE.get(name, 'purpose not documented')})"


def redact(text: str) -> str:
    """Remove any known secret value from text before it is printed or stored."""
    cleaned = text
    for name in PURPOSE:
        value = os.environ.get(name)
        if value and len(value) > 6:
            cleaned = cleaned.replace(value, f"<{name} redacted>")
    return cleaned

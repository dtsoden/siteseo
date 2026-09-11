"""Secret names, and how siteseo gets their values.

Values arrive through the process environment and are read from there. They are
never fetched by asking a child process to print them, because a vault worth
using refuses to let that happen: aihsm scrubs stored values out of its child's
output, so an echo-back returns `****` rather than the secret. That is the vault
working correctly, and an earlier version of this file was defeated by it.

So the injection happens one level up. `scripts/cli.py` re-executes bundled
scripts under `aihsm run --set VAR=NAME ...` for every name the vault holds, and
everything here just reads `os.environ`. The value is in the child's environment
and never passes through siteseo's own stdout, argv, logs or history files.

Nothing in this module ever prints a value.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache

#: What each name unlocks, for messages that explain a skip.
PURPOSE = {
    "SITESEO_GSC_SERVICE_ACCOUNT": "Search Console and Analytics (modules J and N)",
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


def vault_available() -> bool:
    return shutil.which("aihsm") is not None


@lru_cache(maxsize=1)
def vault_names() -> frozenset[str]:
    """Names the vault holds. Names only: `aihsm list` never prints values."""
    if not vault_available():
        return frozenset()
    try:
        proc = subprocess.run(
            ["aihsm", "list"], capture_output=True, text=True, timeout=20
        )
    except Exception:
        return frozenset()
    if proc.returncode != 0:
        return frozenset()
    return frozenset(line.strip() for line in proc.stdout.splitlines() if line.strip())


def injectable() -> list[str]:
    """siteseo names the vault can supply, for the launcher to inject."""
    held = vault_names()
    return [name for name in PURPOSE if name in held]


def get(name: str) -> str | None:
    """The secret's value from the environment, or None.

    Populated by the launcher through `aihsm run`. Never reads the vault
    directly, because a vault that let this module read a value back would also
    let anything else read it back.
    """
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


def require(name: str) -> str:
    value = get(name)
    if not value:
        in_vault = name in vault_names()
        hint = (
            f"{name} is in your vault but was not injected into this process. "
            "Run the tool through the siteseo launcher rather than calling the "
            "script directly."
            if in_vault
            else f"{name} is not stored on this machine. Add it with: aihsm put {name}"
        )
        raise MissingSecret(
            f"{name} unlocks {PURPOSE.get(name, 'a paid or authenticated feature')}.\n{hint}"
        )
    return value


def available(name: str) -> bool:
    return get(name) is not None


def describe(name: str) -> str:
    """Safe to print: says whether it resolves and from where, never what it is."""
    if available(name):
        return f"{name}: available ({PURPOSE.get(name, '')})"
    if name in vault_names():
        return f"{name}: in the vault, not injected into this process"
    return f"{name}: not set ({PURPOSE.get(name, '')})"


def redact(text: str) -> str:
    """Remove any injected secret value from text before printing or storing it."""
    cleaned = text
    for name in PURPOSE:
        value = os.environ.get(name)
        if value and len(value) > 6:
            cleaned = cleaned.replace(value, f"<{name} redacted>")
    return cleaned

"""Current and former names for everything siteseoai writes or reads by name.

The tool was called siteseo before it was renamed siteseoai. Sites audited by
the old version hold a `siteseo.yaml` and a `.siteseo/` folder of committed
history, machines hold vault entries and environment variables named
`SITESEO_*`, and Markdown files carry a `generator: siteseo` marker. None of
that should be lost on upgrade, so every lookup here tries the new name first
and falls back to the old one when the new one is absent. New files are always
written under the new name.

Standard library only: the launcher and `status` import this before the isolated
environment exists.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path

NAME = "siteseoai"
LEGACY_NAME = "siteseo"

CONFIG_NAME = "siteseoai.yaml"
LEGACY_CONFIG_NAME = "siteseo.yaml"

STATE_DIR = ".siteseoai"
LEGACY_STATE_DIR = ".siteseo"

ENV_PREFIX = "SITESEOAI_"
LEGACY_ENV_PREFIX = "SITESEO_"

#: Marker written into generated Markdown, and the one older versions wrote.
MARKDOWN_MARKERS = ("generator: siteseoai", "generator: siteseo")


def config_in(directory: Path) -> Path | None:
    """The config file in one directory, preferring the current name."""
    for name in (CONFIG_NAME, LEGACY_CONFIG_NAME):
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def state_dir(root: Path) -> Path:
    """The site's state folder.

    `.siteseoai/` when it exists or when neither exists. A site that only has the
    `.siteseo/` folder from before the rename keeps using it, so its committed
    history and reports stay in one place. Moving it is one `git mv`.
    """
    current = root / STATE_DIR
    legacy = root / LEGACY_STATE_DIR
    if not current.exists() and legacy.is_dir():
        return legacy
    return current


def legacy_env_name(name: str) -> str | None:
    """`SITESEOAI_X` becomes `SITESEO_X`. Anything else has no former name."""
    if name.startswith(ENV_PREFIX):
        return LEGACY_ENV_PREFIX + name[len(ENV_PREFIX):]
    return None


def getenv(name: str, environ: MutableMapping[str, str] | None = None) -> str | None:
    """An environment variable, falling back to its pre-rename name."""
    environ = os.environ if environ is None else environ
    value = environ.get(name)
    if value is not None and value.strip():
        return value
    legacy = legacy_env_name(name)
    if legacy:
        value = environ.get(legacy)
        if value is not None and value.strip():
            return value
    return None


def adopt_legacy_env(environ: MutableMapping[str, str] | None = None) -> list[str]:
    """Copy each `SITESEO_X` into `SITESEOAI_X` where the new name is unset.

    Returns the new names that were filled, for a doctor note. Values are never
    printed.
    """
    environ = os.environ if environ is None else environ
    adopted = []
    for key in list(environ):
        if not key.startswith(LEGACY_ENV_PREFIX) or key.startswith(ENV_PREFIX):
            continue
        new = ENV_PREFIX + key[len(LEGACY_ENV_PREFIX):]
        if not (environ.get(new) or "").strip() and (environ.get(key) or "").strip():
            environ[new] = environ[key]
            adopted.append(new)
    return adopted


def is_generated_markdown(text: str) -> bool:
    return any(marker in text for marker in MARKDOWN_MARKERS)

"""Isolated Python environment resolution for siteseo.

The environment lives OUTSIDE the plugin directory, because a plugin update
replaces the plugin directory wholesale and would otherwise destroy it. It is
keyed by a hash of requirements.txt, so changing a dependency produces a new
environment rather than a silent mismatch against the old one.

Locations:
    Windows   %LOCALAPPDATA%\\siteseo\\runtime\\<key>
    macOS     ~/Library/Application Support/siteseo/runtime/<key>
    Linux     ~/.local/share/siteseo/runtime/<key>   (respects XDG_DATA_HOME)

Nothing here ever installs into a global or user-level site-packages.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = PLUGIN_ROOT / "requirements.txt"

# Bumped when the environment layout itself changes, independent of deps.
LAYOUT_VERSION = "1"


class SetupRequired(RuntimeError):
    """Raised when the environment is missing or stale."""


def data_home() -> Path:
    """Per-user writable data directory, by platform convention."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base)
        return Path.home() / "AppData" / "Local"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".local" / "share"


def requirements_key() -> str:
    """Short stable key derived from the pinned requirements.

    Line endings are normalised before hashing. Git rewrites them per platform,
    so hashing raw bytes would give a Windows checkout and a macOS checkout
    different keys for identical dependencies, and each machine would build a
    second environment for no reason.
    """
    if not REQUIREMENTS.is_file():
        raise SetupRequired(f"requirements.txt not found at {REQUIREMENTS}")
    normalised = REQUIREMENTS.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    digest = hashlib.sha256(normalised).hexdigest()
    return f"v{LAYOUT_VERSION}-{digest[:12]}"


def env_dir() -> Path:
    return data_home() / "siteseo" / "runtime" / requirements_key()


def env_python(env: Path | None = None) -> Path:
    env = env or env_dir()
    if sys.platform == "win32":
        return env / "Scripts" / "python.exe"
    return env / "bin" / "python"


def marker_path(env: Path | None = None) -> Path:
    return (env or env_dir()) / ".siteseo-ready"


def is_ready() -> bool:
    return env_python().is_file() and marker_path().is_file()


def find_uv() -> str | None:
    found = shutil.which("uv")
    if found:
        return found
    # uv's own installer puts it here and does not always update PATH for
    # non-login shells.
    candidates = [
        Path.home() / ".local" / "bin" / ("uv.exe" if sys.platform == "win32" else "uv"),
        Path.home() / ".cargo" / "bin" / ("uv.exe" if sys.platform == "win32" else "uv"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def _run(cmd: list[str], label: str) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise SetupRequired(f"{label} failed:\n{detail}")


def create_env(verbose: bool = True, force: bool = False) -> Path:
    """Build the isolated environment. Prefers uv, falls back to venv plus pip.

    An environment that already matches the current requirements is reused.
    Rebuilding it every time `setup` runs would make `setup --chromium` fail on
    a machine that is already set up, which is exactly when it gets used.
    """
    env = env_dir()

    if is_ready() and not force:
        if verbose:
            print(f"Environment: {env}")
            print("Builder:     already built for these requirements, reusing it")
            print("             pass --force to rebuild from scratch")
        return env

    env.parent.mkdir(parents=True, exist_ok=True)

    uv = find_uv()
    if verbose:
        print(f"Environment: {env}")
        print(f"Builder:     {'uv' if uv else 'venv + pip'}")

    if uv:
        _run([uv, "venv", "--clear", "--python", "3.11", str(env)], "uv venv")
        _run(
            [uv, "pip", "install", "--python", str(env_python(env)), "-r", str(REQUIREMENTS)],
            "uv pip install",
        )
    else:
        _run([sys.executable, "-m", "venv", str(env)], "python -m venv")
        python = str(env_python(env))
        _run([python, "-m", "pip", "install", "--upgrade", "pip"], "pip upgrade")
        _run([python, "-m", "pip", "install", "-r", str(REQUIREMENTS)], "pip install")

    marker_path(env).write_text(requirements_key(), encoding="utf-8")
    return env


def install_chromium(verbose: bool = True) -> tuple[bool, str]:
    """Install Playwright's Chromium. Optional: only module A rendering needs it."""
    if not is_ready():
        return False, "environment not built yet"
    proc = subprocess.run(
        [str(env_python()), "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "").strip().splitlines()[-1:][0] if (
            proc.stderr or proc.stdout
        ) else "unknown error"
    if verbose:
        print("Chromium installed.")
    return True, "installed"


def chromium_ready() -> bool:
    if not is_ready():
        return False
    # executable_path reports where Chromium WOULD live, whether or not it has
    # been downloaded, so the path alone proves nothing. Check the file is
    # actually on disk: reporting a missing browser as ready would make module
    # A's rendered-DOM check look like it ran when it never could.
    probe = (
        "import sys\n"
        "from pathlib import Path\n"
        "try:\n"
        "    from playwright.sync_api import sync_playwright\n"
        "    with sync_playwright() as p:\n"
        "        found = Path(p.chromium.executable_path).is_file()\n"
        "    sys.exit(0 if found else 1)\n"
        "except Exception:\n"
        "    sys.exit(1)\n"
    )
    proc = subprocess.run([str(env_python()), "-c", probe], capture_output=True, text=True)
    return proc.returncode == 0


def require_env() -> Path:
    """Return the environment's interpreter, or explain how to build it."""
    if not is_ready():
        raise SetupRequired(
            "siteseo runtime is not set up on this machine.\n"
            "Run /siteseo setup (or `scripts/siteseo setup` from the repo)."
        )
    return env_python()

"""The runtime must resolve the same way on every machine.

These are the failures that only show up after the plugin is installed somewhere
else, which is the worst time to find them.
"""

from __future__ import annotations

import re
import sys
import runtime


def test_requirements_key_ignores_line_endings(tmp_path, monkeypatch):
    """Git rewrites line endings per platform. The key must not notice.

    Hashing raw bytes would give a Windows checkout and a macOS checkout
    different keys for identical dependencies, so each machine would build a
    second environment and neither would reuse the other's.
    """
    content = "selectolax==0.3.27\nhttpx==0.28.1\n"

    unix = tmp_path / "unix.txt"
    unix.write_bytes(content.encode())
    windows = tmp_path / "windows.txt"
    windows.write_bytes(content.replace("\n", "\r\n").encode())

    monkeypatch.setattr(runtime, "REQUIREMENTS", unix)
    unix_key = runtime.requirements_key()
    monkeypatch.setattr(runtime, "REQUIREMENTS", windows)
    windows_key = runtime.requirements_key()

    assert unix_key == windows_key


def test_requirements_key_changes_when_a_dependency_changes(tmp_path, monkeypatch):
    """A changed pin must produce a new environment, not reuse a stale one."""
    first = tmp_path / "a.txt"
    first.write_text("httpx==0.28.1\n", encoding="utf-8")
    second = tmp_path / "b.txt"
    second.write_text("httpx==0.28.2\n", encoding="utf-8")

    monkeypatch.setattr(runtime, "REQUIREMENTS", first)
    key_one = runtime.requirements_key()
    monkeypatch.setattr(runtime, "REQUIREMENTS", second)
    key_two = runtime.requirements_key()

    assert key_one != key_two


def test_environment_lives_outside_the_plugin_directory():
    """A plugin update replaces the plugin directory. The environment must survive."""
    env = runtime.env_dir().resolve()
    plugin = runtime.PLUGIN_ROOT.resolve()
    assert plugin not in env.parents
    assert env != plugin


def test_environment_path_is_platform_appropriate():
    parts = runtime.env_dir().parts
    assert "siteseo" in parts and "runtime" in parts
    if sys.platform == "win32":
        assert "Local" in parts or "AppData" in parts
    elif sys.platform == "darwin":
        assert "Application Support" in parts
    else:
        assert ".local" in parts or "share" in parts


def test_launcher_has_unix_line_endings(repo_root):
    """A CRLF launcher will not run on macOS or Linux after a Windows checkout."""
    launcher = (repo_root / "scripts" / "siteseo").read_bytes()
    assert b"\r\n" not in launcher, "scripts/siteseo must keep LF endings"
    assert launcher.startswith(b"#!/usr/bin/env bash")


def test_gitattributes_pins_the_launcher_to_lf(repo_root):
    text = (repo_root / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"scripts/siteseo\s+text\s+eol=lf", text)


def test_launcher_refuses_paths_outside_the_plugin(tmp_path):
    """`run` must not be a way to execute an arbitrary file."""
    import cli

    assert cli.cmd_run(["../../etc/passwd"]) == 2
    assert cli.cmd_run([str(tmp_path / "anything.py")]) == 2


def test_no_script_hardcodes_an_interpreter_path(repo_root):
    """Every tool goes through the launcher, which resolves the interpreter."""
    offenders = []
    for path in (repo_root / "scripts").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"#!.*python|/usr/bin/python|C:\\\\Python", text):
            offenders.append(f"{path.name}: {match.group(0)}")
    assert not offenders, offenders


def test_requirements_are_pinned_exactly(repo_root):
    """An unpinned dependency makes two machines disagree silently."""
    text = (repo_root / "requirements.txt").read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        assert "==" in line, f"{line!r} is not pinned to an exact version"


def test_vendored_licence_files_are_present_for_every_source(repo_root):
    import json

    lock = json.loads((repo_root / "upstream.lock").read_text(encoding="utf-8"))
    for source in lock["sources"]:
        folder = repo_root / "vendor" / source["repo"].split("/")[-1]
        assert (folder / "LICENSE").is_file()


def test_setup_reuses_a_matching_environment(monkeypatch):
    """`setup --chromium` on an already-built machine must not fail.

    uv refuses to create a virtual environment over an existing one, so
    rebuilding unconditionally made setup fail exactly when someone ran it to
    add Chromium to a working install.
    """
    calls = []
    monkeypatch.setattr(runtime, "is_ready", lambda: True)
    monkeypatch.setattr(runtime, "_run", lambda cmd, label: calls.append(label))

    runtime.create_env(verbose=False)
    assert calls == [], "a matching environment must be reused, not rebuilt"

    runtime.create_env(verbose=False, force=True)
    assert calls, "--force must actually rebuild"


def test_chromium_probe_requires_the_binary_to_exist():
    """executable_path reports where Chromium would live, installed or not.

    Trusting the path alone reported a browser that was never downloaded as
    ready, which would make module A's rendered-DOM check look like it ran.
    """
    import inspect

    body = inspect.getsource(runtime.chromium_ready)
    assert "is_file()" in body, "the probe must check the binary is on disk"

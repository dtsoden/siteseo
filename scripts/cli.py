"""siteseo command dispatcher.

Runs under the BOOTSTRAP interpreter, which only has the standard library.
Nothing in this file may import a third-party package. Its job is to resolve
the isolated environment and re-exec the requested script inside it.

    siteseo setup            build or refresh the isolated environment
    siteseo doctor [--json]  runtime, secrets and staleness report
    siteseo run <script.py>  run a bundled script inside the environment
    siteseo version
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import runtime  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
VERSION = "0.1.3"

USAGE = """siteseo <command> [args]

  setup             build the isolated Python environment, or reuse a matching one
  setup --chromium  also install Playwright's Chromium (module A rendering)
  setup --force     rebuild the environment from scratch
  doctor [--json]   report runtime, secrets and reference staleness
  run <script.py>   run a bundled script inside the environment
  version

Every bundled tool is invoked through `run`. Never call a bundled script with a
bare interpreter: it will not see the pinned dependencies.
"""


def cmd_setup(argv: list[str]) -> int:
    want_chromium = "--chromium" in argv
    force = "--force" in argv
    print("siteseo setup")
    try:
        runtime.create_env(force=force)
    except runtime.SetupRequired as exc:
        print(f"\nSetup failed.\n{exc}", file=sys.stderr)
        return 1
    print("Core environment ready.")

    if want_chromium:
        ok, detail = runtime.install_chromium()
        print(f"Chromium: {'ready' if ok else 'not installed (' + detail + ')'}")
    else:
        print(
            "Chromium: skipped. Module A's rendered-DOM check needs it.\n"
            "          Run `siteseo setup --chromium` to add it."
        )
    print("\nNext: siteseo doctor")
    return 0


def cmd_run(argv: list[str]) -> int:
    if not argv:
        print("run needs a script name, for example: run crawl.py", file=sys.stderr)
        return 2

    name = argv[0]
    if name.endswith(".py"):
        name = name[:-3]
    # Reject traversal and absolute paths: only bundled scripts may run.
    if Path(name).is_absolute() or ".." in Path(name).parts:
        print(f"Refusing to run a path outside the plugin: {argv[0]}", file=sys.stderr)
        return 2

    target = (SCRIPTS / f"{name}.py").resolve()
    try:
        target.relative_to(SCRIPTS)
    except ValueError:
        print(f"Refusing to run a path outside the plugin: {argv[0]}", file=sys.stderr)
        return 2
    if not target.is_file():
        print(f"No bundled script named {argv[0]}", file=sys.stderr)
        return 2

    try:
        python = runtime.require_env()
    except runtime.SetupRequired as exc:
        print(str(exc), file=sys.stderr)
        return 3

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(SCRIPTS), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    env["SITESEO_PLUGIN_ROOT"] = str(runtime.PLUGIN_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"

    return subprocess.run([str(python), str(target), *argv[1:]], env=env).returncode


def cmd_doctor(argv: list[str]) -> int:
    # doctor runs under the bootstrap interpreter on purpose: it has to be able
    # to report that the environment is missing.
    sys.argv = ["doctor.py", *argv]
    import doctor

    return doctor.main()


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(USAGE)
        return 0

    command, rest = argv[0], argv[1:]
    if command == "setup":
        return cmd_setup(rest)
    if command == "doctor":
        return cmd_doctor(rest)
    if command == "run":
        return cmd_run(rest)
    if command in {"version", "--version", "-V"}:
        print(f"siteseo {VERSION}")
        return 0

    print(f"Unknown command: {command}\n\n{USAGE}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

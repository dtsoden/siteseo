# Install

Checked against official documentation on 2026-10-14.

siteseo is a Claude Code plugin. Installing it takes two commands inside Claude
Code, and building its Python environment takes one more.

## Prerequisites

- [Claude Code](https://code.claude.com/docs).
- Python 3.11 or newer on your PATH. siteseo's launcher uses it only to start
  and installs nothing into it. If it is missing, the launcher prints the
  install command for your system:

  ```
  macOS    brew install python@3.12
  Windows  winget install Python.Python.3.12
  Linux    your distribution's python3.12 package
  ```

  If Python is installed somewhere unusual, point siteseo at it with
  `SITESEO_PYTHON=/full/path/to/python`.

- [uv](https://docs.astral.sh/uv/getting-started/installation/), recommended
  but optional. siteseo builds its environment with uv when it finds it and falls
  back to Python's own venv and pip when it does not. The official installers:

  ```
  macOS and Linux   curl -LsSf https://astral.sh/uv/install.sh | sh
  Windows           powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

  It installs to `~/.local/bin` (`%USERPROFILE%\.local\bin` on Windows), and
  siteseo looks there even when that folder is not on your PATH yet.

## Install the plugin

In Claude Code:

```
/plugin marketplace add dtsoden/siteseo
/plugin install siteseo@dtsoden-siteseo
```

`dtsoden-siteseo` is the marketplace's name, as declared in this repository's
`.claude-plugin/marketplace.json`. The install command opens a panel where you
choose a scope before anything installs. See Anthropic's
[plugin documentation](https://code.claude.com/docs/en/discover-plugins) for
what each scope means.

## Build the environment

```
/siteseo setup
/siteseo doctor
```

`setup` builds an isolated Python environment outside the plugin directory, so
updating the plugin does not destroy it. It is keyed by a hash of the pinned
requirements, so a dependency change triggers a rebuild instead of a silent
mismatch. Nothing goes into your system or user Python.

One check in module A renders pages in a headless browser to compare the
rendered DOM with the raw HTML. It needs Chromium, which is a large download, so
it is opt-in:

```
"${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" setup --chromium
```

Without it, that one check is skipped and the report says so.

## Updating

Claude Code has no `/plugin update` slash command. Update siteseo either way:

- In a session, run `/plugin`, open the **Installed** tab, select siteseo and
  choose **Update now**.
- From a shell, run `claude plugin update siteseo@dtsoden-siteseo`.

Then run `/reload-plugins`, followed by `/siteseo doctor`. If the update changed
a pinned dependency, doctor tells you to run `/siteseo setup` again.

Auto-update is off by default for marketplaces Anthropic does not run, so an
update happens only when you ask for one.

Next: [store your secrets](02-secrets.md).

Sources:
[Claude Code plugins](https://code.claude.com/docs/en/discover-plugins),
[plugin CLI reference](https://code.claude.com/docs/en/plugins/cli-reference),
[uv installation](https://docs.astral.sh/uv/getting-started/installation/),
[uv storage locations](https://docs.astral.sh/uv/reference/storage/).

[Docs home](../README.md) / [Setup guide](README.md) / Install

# Install

Checked against official documentation on 2026-10-14.

siteseoai is a Claude Code plugin. Installing it takes two commands inside Claude
Code, and building its Python environment takes one more.

## Prerequisites

- [Claude Code](https://code.claude.com/docs).
- Python 3.11 or newer on your PATH. siteseoai's launcher uses it only to start
  and installs nothing into it. If it is missing, the launcher prints the
  install command for your system:

  ```
  macOS    brew install python@3.12
  Windows  winget install Python.Python.3.12
  Linux    your distribution's python3.12 package
  ```

  If Python is installed somewhere unusual, point siteseoai at it with
  `SITESEOAI_PYTHON=/full/path/to/python`.

- [uv](https://docs.astral.sh/uv/getting-started/installation/), recommended
  but optional. siteseoai builds its environment with uv when it finds it and falls
  back to Python's own venv and pip when it does not. The official installers:

  ```
  macOS and Linux   curl -LsSf https://astral.sh/uv/install.sh | sh
  Windows           powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

  It installs to `~/.local/bin` (`%USERPROFILE%\.local\bin` on Windows), and
  siteseoai looks there even when that folder is not on your PATH yet.

## Install the plugin

In Claude Code:

```
/plugin marketplace add dtsoden/siteseoai
/plugin install siteseoai@dtsoden-siteseoai
```

`dtsoden-siteseoai` is the marketplace's name, as declared in this repository's
`.claude-plugin/marketplace.json`. The install command opens a panel where you
choose a scope before anything installs. See Anthropic's
[plugin documentation](https://code.claude.com/docs/en/discover-plugins) for
what each scope means.

## Build the environment

```
/siteseoai setup
/siteseoai doctor
```

`setup` builds an isolated Python environment outside the plugin directory, so
updating the plugin does not destroy it. It is keyed by a hash of the pinned
requirements, so a dependency change triggers a rebuild instead of a silent
mismatch. Nothing goes into your system or user Python.

A healthy `doctor` looks like this. The missing keys are normal: every one of
them is optional, and a missing key shrinks a run rather than failing it.

```
Runtime
  ok   bootstrap Python 3.11.9 on win32
  ok   uv found
  ok   isolated environment
  MISS Chromium  (module A rendered-DOM check will be skipped)

Secrets on this machine (names only, values are never read here)
  MISS SITESEOAI_PAGESPEED_API_KEY
       unlocks: PageSpeed Insights and CrUX (module D)

Reference data freshness
  ok   ai-bots.yaml  verified 2026-09-11 (0 days ago)
  ok   checks.yaml   verified 2026-09-11 (0 days ago)

Ready to audit.
```

One check in module A renders pages in a headless browser to compare the
rendered DOM with the raw HTML. It needs Chromium, which is a large download, so
it is opt-in:

```
"${CLAUDE_PLUGIN_ROOT}/scripts/siteseoai" setup --chromium
```

Without it, that one check is skipped and the report says so.

## Updating

Claude Code has no `/plugin update` slash command. Update siteseoai either way:

- In a session, run `/plugin`, open the **Installed** tab, select siteseoai and
  choose **Update now**.
- From a shell, run `claude plugin update siteseoai@dtsoden-siteseoai`.

Then run `/reload-plugins`, followed by `/siteseoai doctor`. If the update changed
a pinned dependency, doctor tells you to run `/siteseoai setup` again.

Auto-update is off by default for marketplaces Anthropic does not run, so an
update happens only when you ask for one.

## Moving from siteseo

This plugin used to be called siteseo, installed as `siteseo@dtsoden-siteseo`
and run as `/siteseo`. The new name is a new plugin as far as Claude Code is
concerned, so install it with the two lines above and then remove the old one:

```
/plugin uninstall siteseo@dtsoden-siteseo
/plugin marketplace remove dtsoden-siteseo
```

Nothing you set up under the old name is lost:

- A site with `siteseo.yaml` keeps working. `siteseoai.yaml` wins when both
  exist, so rename the file whenever it suits you.
- A site with a `.siteseo/` folder keeps writing its history and reports there
  until a `.siteseoai/` folder exists. To move it, run
  `git mv .siteseo .siteseoai` and commit.
- Secrets stored in the vault or set in the environment as `SITESEO_*` are still
  found. The `SITESEOAI_*` name is used first when both are set. The same goes
  for `SITESEO_PYTHON`, `SITESEO_OFFLINE` and `SITESEO_PLUGIN_ROOT`.
- The isolated environment built under the old `siteseo` data folder is reused
  until its dependencies change, so there is nothing to rebuild.
- Markdown files and `llms.txt` written by siteseo are still recognized as
  generated, so a re-export updates them instead of skipping them.
- If `/siteseoai markdown --setup` finds a serving file under its old
  `siteseo-markdown` name, it compares against that file rather than adding a
  second copy.

The test suite runs on Windows, macOS and Linux, because a tool that installs
on one of them is not portable.

Sources:
[Claude Code plugins](https://code.claude.com/docs/en/discover-plugins),
[plugin CLI reference](https://code.claude.com/docs/en/plugins/cli-reference),
[uv installation](https://docs.astral.sh/uv/getting-started/installation/),
[uv storage locations](https://docs.astral.sh/uv/reference/storage/).

---

Previous: [Setup guide](README.md) | Next: [Storing secrets](02-secrets.md)

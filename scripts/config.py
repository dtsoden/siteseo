"""Load and validate a site's siteseo.yaml.

Fails with a message that names the offending field. A config error should never
surface as a stack trace three modules later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

CONFIG_NAME = "siteseo.yaml"
STATE_DIR = ".siteseo"

STACKS = {"auto", "astro", "next", "hugo", "eleventy", "plain-html", "other"}
HOSTS = {"netlify", "vercel", "cloudflare-pages", "github-pages", "other"}
POLICY_VALUES = {"allow", "block"}


class ConfigError(ValueError):
    """A siteseo.yaml problem, phrased for a human."""


@dataclass
class AIPolicy:
    search_and_user_fetch: str = "allow"
    training: str = "allow"


@dataclass
class Budget:
    monthly_usd: float = 0.0


@dataclass
class Config:
    site: str
    root: Path
    stack: str = "auto"
    build_dir: str | None = None
    serve_cmd: str | None = None
    host: str = "other"
    templates: list[str] = field(default_factory=lambda: ["/"])
    ai_policy: AIPolicy = field(default_factory=AIPolicy)
    prompts: list[str] = field(default_factory=list)
    competitors: list[str] = field(default_factory=list)
    budget: Budget = field(default_factory=Budget)
    secrets: str = "env"

    @property
    def origin(self) -> str:
        parsed = urlparse(self.site)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def build_path(self) -> Path | None:
        if not self.build_dir:
            return None
        return (self.root / self.build_dir).resolve()

    @property
    def state_dir(self) -> Path:
        return self.root / STATE_DIR

    @property
    def history_dir(self) -> Path:
        return self.state_dir / "history"

    @property
    def reports_dir(self) -> Path:
        return self.state_dir / "reports"

    @property
    def imports_dir(self) -> Path:
        return self.state_dir / "imports"

    def ensure_dir(self, path: Path) -> Path:
        """Create one state directory, at the moment something writes to it.

        Creating all three up front left empty `reports/` and `imports/` folders
        sitting in the repo after an audit, which reads as something having
        failed. A directory should appear because a file went into it.
        """
        path.mkdir(parents=True, exist_ok=True)
        return path

    def to_dict(self) -> dict[str, Any]:
        return {
            "site": self.site,
            "stack": self.stack,
            "build_dir": self.build_dir,
            "host": self.host,
            "templates": self.templates,
            "ai_policy": {
                "search_and_user_fetch": self.ai_policy.search_and_user_fetch,
                "training": self.ai_policy.training,
            },
            "prompt_count": len(self.prompts),
            "competitors": self.competitors,
            "budget_monthly_usd": self.budget.monthly_usd,
        }


def find_config(start: Path | None = None) -> Path | None:
    """Walk up from `start` looking for siteseo.yaml."""
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def _require_str(raw: dict, key: str, where: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: `{key}` is required and must be a non-empty string")
    return value.strip()


def _opt_str(raw: dict, key: str, where: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: `{key}` must be a non-empty string when present")
    return value.strip()


def _str_list(raw: dict, key: str, where: str, default: list[str] | None = None) -> list[str]:
    value = raw.get(key)
    if value is None:
        return list(default or [])
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise ConfigError(f"{where}: `{key}` must be a list of strings")
    return [x.strip() for x in value if x.strip()]


def parse(raw: dict[str, Any], root: Path, where: str) -> Config:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: the file must contain a mapping at the top level")

    site = _require_str(raw, "site", where)
    parsed = urlparse(site)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(f"{where}: `site` must be a full URL, for example https://example.com")

    stack = (_opt_str(raw, "stack", where) or "auto").lower()
    if stack not in STACKS:
        raise ConfigError(f"{where}: `stack` must be one of {sorted(STACKS)}, got {stack!r}")

    host = (_opt_str(raw, "host", where) or "other").lower()
    if host not in HOSTS:
        raise ConfigError(f"{where}: `host` must be one of {sorted(HOSTS)}, got {host!r}")

    templates = _str_list(raw, "templates", where, default=["/"])
    for template in templates:
        if not template.startswith("/"):
            raise ConfigError(
                f"{where}: template {template!r} must be a site-root path starting with /"
            )

    policy_raw = raw.get("ai_policy") or {}
    if not isinstance(policy_raw, dict):
        raise ConfigError(f"{where}: `ai_policy` must be a mapping")
    policy = AIPolicy()
    for key in ("search_and_user_fetch", "training"):
        if key in policy_raw:
            value = str(policy_raw[key]).lower()
            if value not in POLICY_VALUES:
                raise ConfigError(
                    f"{where}: `ai_policy.{key}` must be allow or block, got {policy_raw[key]!r}"
                )
            setattr(policy, key, value)

    budget_raw = raw.get("budget") or {}
    if not isinstance(budget_raw, dict):
        raise ConfigError(f"{where}: `budget` must be a mapping")
    monthly = budget_raw.get("monthly_usd", 0)
    try:
        monthly = float(monthly)
    except (TypeError, ValueError):
        raise ConfigError(f"{where}: `budget.monthly_usd` must be a number") from None
    if monthly < 0:
        raise ConfigError(f"{where}: `budget.monthly_usd` cannot be negative")

    secrets = (_opt_str(raw, "secrets", where) or "env").lower()
    if secrets not in {"env", "vault"}:
        raise ConfigError(f"{where}: `secrets` must be env or vault")

    build_dir = _opt_str(raw, "build_dir", where)
    if build_dir:
        resolved = (root / build_dir).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            raise ConfigError(
                f"{where}: `build_dir` must stay inside the site repo, got {build_dir!r}"
            ) from None

    return Config(
        site=site.rstrip("/"),
        root=root,
        stack=stack,
        build_dir=build_dir,
        serve_cmd=_opt_str(raw, "serve_cmd", where),
        host=host,
        templates=templates,
        ai_policy=policy,
        prompts=_str_list(raw, "prompts", where),
        competitors=_str_list(raw, "competitors", where),
        budget=Budget(monthly_usd=monthly),
        secrets=secrets,
    )


def load(path: Path | None = None, start: Path | None = None) -> Config:
    path = path or find_config(start)
    if path is None:
        raise ConfigError(
            f"No {CONFIG_NAME} found in this directory or any parent.\n"
            f"Create one, or run `siteseo run config.py --init` to write a starter file."
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: not valid YAML\n{exc}") from None
    return parse(raw, path.parent.resolve(), where=str(path))


STARTER = """# siteseo configuration. Commit this file.
# Secrets never go here: only names. Values live in your OS vault.
site: https://example.com

# auto, astro, next, hugo, eleventy, plain-html, other
stack: auto

# Directory holding built HTML. Auditing this catches problems before deploy.
build_dir: dist

# Optional. Used when a check needs a real HTTP server rather than files.
serve_cmd: npx serve dist -l 4173

# netlify, vercel, cloudflare-pages, github-pages, other
host: other

# One sample URL per page template. Performance tests run against these.
templates:
  - /

# What you want AI crawlers to be able to do. siteseo flags any mismatch
# between this and what robots.txt and your CDN actually do, in both directions.
ai_policy:
  search_and_user_fetch: allow   # OAI-SearchBot, ChatGPT-User, Claude-SearchBot,
                                 # Claude-User, PerplexityBot, Perplexity-User
  training: allow                # GPTBot, ClaudeBot, Google-Extended,
                                 # Applebot-Extended, CCBot

# Questions a real customer would type. Used by `siteseo track`.
prompts: []

competitors: []

budget:
  monthly_usd: 0

secrets: env
"""


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Load or create siteseo.yaml")
    parser.add_argument("--init", action="store_true", help="write a starter siteseo.yaml here")
    parser.add_argument("--json", action="store_true", help="print the loaded config as JSON")
    args = parser.parse_args()

    if args.init:
        target = Path.cwd() / CONFIG_NAME
        if target.exists():
            print(f"{target} already exists. Leaving it alone.")
            return 1
        target.write_text(STARTER, encoding="utf-8")
        print(f"Wrote {target}\nEdit `site` and `build_dir`, then run: siteseo doctor")
        return 0

    try:
        cfg = load()
    except ConfigError as exc:
        print(str(exc))
        return 1

    if args.json:
        print(json.dumps(cfg.to_dict(), indent=2))
    else:
        print(f"site      {cfg.site}")
        print(f"root      {cfg.root}")
        print(f"stack     {cfg.stack}")
        print(f"build_dir {cfg.build_dir or '(none: live URL auditing only)'}")
        print(f"templates {', '.join(cfg.templates)}")
        print(f"ai_policy search_and_user_fetch={cfg.ai_policy.search_and_user_fetch} "
              f"training={cfg.ai_policy.training}")
        print(f"budget    ${cfg.budget.monthly_usd:.2f} per month")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

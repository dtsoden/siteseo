"""Module E: AI crawler access.

Three independent tests per crawler, because each one can disagree with the
others and the disagreement is usually the finding:

  1. robots  What robots.txt says for this crawler's token, under RFC 9309
             precedence.
  2. fetch   What the site actually returns when the request carries that
             crawler's User-Agent string. A CDN bot rule can block a crawler
             that robots.txt allows.
  3. policy  What ai_policy in siteseo.yaml says you intended.

It also compares the robots.txt served live against the one in the repo, because
a CDN can add Disallow lines or return 403 to AI crawlers with no change in your
source at all.

A 200 from a spoofed user agent proves only that robots rules and user-agent
filtering did not block the request. Some operators verify crawler IP ranges, so
the real crawler could still be refused. That limit is printed with the results.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import findings as F
import robots_check
from source import BuildSource, LiveSource, Source

SAMPLE_LIMIT = 5
SPOOF_CAVEAT = (
    "A 200 here means robots rules and user-agent filtering did not block the "
    "request. Operators that verify crawler IP ranges could still refuse the "
    "real crawler. Bot-hit logs are what confirm access."
)


def reference_dir() -> Path:
    return F.plugin_root() / "skills" / "siteseo" / "reference"


@dataclass
class Bot:
    token: str
    operator: str
    purpose: str
    docs: str
    user_agent: str = ""
    verify: list[str] = field(default_factory=lambda: ["robots", "fetch"])
    note: str = ""

    @property
    def policy_key(self) -> str:
        return "training" if self.purpose == "training" else "search_and_user_fetch"

    @property
    def fetches(self) -> bool:
        return "fetch" in self.verify and bool(self.user_agent)


def load_bots() -> list[Bot]:
    path = reference_dir() / "ai-bots.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [Bot(**entry) for entry in raw.get("bots", [])]


@dataclass
class BotResult:
    bot: Bot
    robots_allowed: bool
    robots_rule: str
    intended: str
    fetch_statuses: dict[str, int] = field(default_factory=dict)
    fetch_tested: bool = False

    @property
    def unreachable(self) -> list[str]:
        """Requests that never got a response: DNS failure, timeout, refused.

        Status 0 means the network did not answer. That is not evidence the
        crawler was blocked, so it is reported separately and never counted
        against AI access.
        """
        return [url for url, status in self.fetch_statuses.items() if status == 0]

    @property
    def fetch_reached(self) -> bool:
        return bool(self.fetch_statuses) and len(self.unreachable) < len(self.fetch_statuses)

    @property
    def fetch_blocked(self) -> list[str]:
        return [url for url, status in self.fetch_statuses.items() if status in (401, 403, 429)]

    @property
    def fetch_errors(self) -> list[str]:
        return [
            url
            for url, status in self.fetch_statuses.items()
            if status not in (0, 200, 401, 403, 429)
        ]

    #: Statuses an ordinary visitor gets for the same URLs, set by run().
    baseline: dict[str, int] = field(default_factory=dict)

    @property
    def blocked_for_bot_only(self) -> list[str]:
        """Refusals a browser does not also receive."""
        return [
            url for url in self.fetch_blocked
            if self.baseline.get(url, 200) != self.fetch_statuses.get(url)
        ]

    @property
    def effective_allowed(self) -> bool:
        if not self.robots_allowed:
            return False
        if self.fetch_tested and self.fetch_reached and self.blocked_for_bot_only:
            return False
        return True

    @property
    def matches_policy(self) -> bool:
        want_allowed = self.intended == "allow"
        return self.effective_allowed == want_allowed


def _repo_robots(cfg) -> tuple[str | None, Path | None]:
    """Find robots.txt in the repo, checking build output then common sources."""
    candidates = []
    if cfg.build_path:
        candidates.append(cfg.build_path / "robots.txt")
    candidates += [
        cfg.root / "public" / "robots.txt",
        cfg.root / "static" / "robots.txt",
        cfg.root / "src" / "robots.txt",
        cfg.root / "robots.txt",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8", errors="replace"), candidate
    return None, None


def _sample_urls(cfg, src: Source) -> list[str]:
    """The homepage plus up to five representative pages."""
    urls = [src.absolute("/")]
    for template in cfg.templates:
        if template != "/":
            urls.append(src.absolute(template))
    if isinstance(src, BuildSource) and len(urls) <= SAMPLE_LIMIT:
        for url, _ in src.walk_pages():
            if url not in urls:
                urls.append(url)
            if len(urls) > SAMPLE_LIMIT:
                break
    return urls[: SAMPLE_LIMIT + 1]


def run(cfg, *, live: bool = False, skip_fetch: bool = False) -> dict:
    """Evaluate every crawler. Returns a JSON-serialisable result."""
    out: dict = {
        "module": "E",
        "site": cfg.site,
        "bots": [],
        "findings": [],
        "notes": [],
        "robots_source": None,
    }
    emitted: list[F.Finding] = []

    repo_text, repo_path = _repo_robots(cfg)

    # Live robots.txt, needed for the repo-versus-served comparison and for the
    # authoritative rules. The gate runs with skip_fetch and uses the repo copy.
    live_text: str | None = None
    live_status = 200
    if not skip_fetch:
        with LiveSource(cfg.origin) as live_src:
            resp = live_src.fetch("/robots.txt")
            live_status = resp.status
            if resp.error:
                out["notes"].append(f"could not fetch live robots.txt: {resp.error}")
            elif resp.status >= 500:
                emitted.append(
                    F.make(
                        "robots.unreachable",
                        f"{cfg.origin}/robots.txt",
                        f"served {resp.status}",
                    )
                )
            else:
                live_text = resp.text()

    if live_text is not None:
        text, out["robots_source"] = live_text, "live"
    elif repo_text is not None:
        text, out["robots_source"] = repo_text, f"repo ({repo_path})"
        live_status = 200
    else:
        text, out["robots_source"] = "", "none found"
        live_status = 404

    robots = robots_check.parse(text, fetch_status=live_status)

    for error in robots.errors:
        emitted.append(
            F.make(
                "robots.invalid_syntax",
                f"{cfg.origin}/robots.txt",
                f"line {error.line_number}: {error.reason} ({error.line!r})",
            )
        )

    if not robots.sitemaps and live_status == 200 and text.strip():
        emitted.append(
            F.make(
                "robots.no_sitemap_line",
                f"{cfg.origin}/robots.txt",
                "robots.txt contains no Sitemap line",
            )
        )

    # The repo-versus-served comparison. This is how a CDN rewrite gets caught.
    if repo_text is not None and live_text is not None:
        if _normalise(repo_text) != _normalise(live_text):
            emitted.append(
                F.make(
                    "ai.robots_live_differs_from_repo",
                    f"{cfg.origin}/robots.txt",
                    _diff_summary(repo_text, live_text, repo_path),
                )
            )

    # Per-crawler evaluation.
    src: Source
    src = LiveSource(cfg.origin) if (live or not cfg.build_path) else BuildSource(
        cfg.build_path, cfg.origin
    )
    samples = _sample_urls(cfg, src)
    home = samples[0]
    src.close()

    policy = {
        "training": cfg.ai_policy.training,
        "search_and_user_fetch": cfg.ai_policy.search_and_user_fetch,
    }

    fetcher = None if skip_fetch else LiveSource(cfg.origin)

    # Baseline every sample URL with an ordinary user agent first. Without it a
    # URL that fails for everyone, a directory with no index page returning 403,
    # reads as every crawler being blocked and drives AI access to near zero.
    # A crawler is only blocked if it fares worse than an ordinary visitor.
    baseline: dict[str, int] = {}
    if fetcher is not None:
        for url in samples:
            baseline[url] = fetcher.fetch(url).status
        broken = [u for u, s in baseline.items() if s != 200]
        if broken:
            out["notes"].append(
                f"{len(broken)} sampled URL(s) do not return 200 for an ordinary "
                f"visitor either, so they say nothing about crawler access: "
                + ", ".join(f"{u} ({baseline[u]})" for u in broken[:3])
            )
    out["baseline"] = baseline

    try:
        for bot in load_bots():
            allowed, rule = robots.decide(bot.token, "/")
            result = BotResult(
                bot=bot,
                robots_allowed=allowed,
                robots_rule=str(rule) if rule else "no matching rule",
                intended=policy[bot.policy_key],
                baseline=baseline,
            )

            if fetcher is not None and bot.fetches:
                for url in samples:
                    resp = fetcher.fetch(url, user_agent=bot.user_agent)
                    result.fetch_statuses[url] = resp.status
                # A run where nothing answered tested nothing.
                result.fetch_tested = result.fetch_reached
                if not result.fetch_tested and result.unreachable:
                    unreachable_note = (
                        f"{bot.token}: no response from {cfg.origin} "
                        f"({len(result.unreachable)} requests). Fetch tests could not run."
                    )
                    if unreachable_note not in out["notes"]:
                        out["notes"].append(unreachable_note)

            _emit_for_bot(result, home, emitted, baseline)
            out["bots"].append(_serialise(result))
    finally:
        if fetcher is not None:
            fetcher.close()

    # llms.txt, reported and never scored.
    _check_llms_txt(cfg, skip_fetch, emitted)
    _check_indexnow(cfg, skip_fetch, emitted)

    if skip_fetch:
        out["notes"].append(
            "fetch tests skipped: robots.txt rules were evaluated, live responses were not"
        )
    else:
        out["notes"].append(SPOOF_CAVEAT)

    merged = F.order(F.merge(emitted))
    out["findings"] = [f.to_dict() for f in merged]
    return out


def _emit_for_bot(result: BotResult, home: str, emitted: list[F.Finding],
                  baseline: dict[str, int] | None = None) -> None:
    bot = result.bot
    baseline = baseline or {}
    label = f"{bot.token} ({bot.operator}, {bot.purpose})"

    if result.intended == "allow" and not result.robots_allowed:
        emitted.append(
            F.make(
                "ai.blocked_against_policy",
                home,
                f"{label} is allowed by policy but robots.txt says: {result.robots_rule}",
                group=bot.token,
                detail={"bot": bot.token, "rule": result.robots_rule, "docs": bot.docs},
            )
        )
    elif result.intended == "block" and result.robots_allowed:
        emitted.append(
            F.make(
                "ai.allowed_against_policy",
                home,
                f"{label} is blocked by policy but robots.txt permits it: {result.robots_rule}",
                group=bot.token,
                detail={"bot": bot.token, "rule": result.robots_rule, "docs": bot.docs},
            )
        )

    if not result.fetch_reached and result.fetch_statuses:
        # Nothing answered. Report nothing rather than inventing a block.
        return

    # A refusal an ordinary visitor also receives is a broken URL, not a blocked
    # crawler. Only a status the crawler gets and a browser does not is evidence.
    bot_only = [
        url for url in result.fetch_blocked
        if baseline.get(url, 200) != result.fetch_statuses.get(url)
    ]

    if result.intended == "allow" and bot_only:
        emitted.append(
            F.make(
                "ai.fetch_non_200",
                bot_only,
                f"{label} received "
                + ", ".join(
                    f"{result.fetch_statuses[u]} at {u} (an ordinary visitor gets "
                    f"{baseline.get(u, 'unknown')})" for u in bot_only[:3]
                )
                + ". robots.txt allows this crawler, so the refusal is coming from "
                "the host or CDN rather than from robots rules.",
                group=bot.token,
                detail={"bot": bot.token, "statuses": result.fetch_statuses, "docs": bot.docs},
            )
        )

    if result.fetch_errors:
        emitted.append(
            F.make(
                "ai.fetch_non_200",
                result.fetch_errors,
                f"{label} received "
                + ", ".join(
                    f"{result.fetch_statuses[u]} at {u}" for u in result.fetch_errors[:3]
                ),
                severity="warning",
                group=bot.token,
                detail={"bot": bot.token, "statuses": result.fetch_statuses},
            )
        )


def _check_llms_txt(cfg, skip_fetch: bool, emitted: list[F.Finding]) -> None:
    present = False
    evidence = ""
    if cfg.build_path and (cfg.build_path / "llms.txt").is_file():
        present, evidence = True, f"{cfg.build_path / 'llms.txt'} exists in the build"
    elif not skip_fetch:
        with LiveSource(cfg.origin) as src:
            resp = src.fetch("/llms.txt")
            present = resp.ok
            evidence = f"{cfg.origin}/llms.txt returned {resp.status}"
    else:
        evidence = "not present in build output"

    emitted.append(
        F.make(
            "ai.llms_txt_present" if present else "ai.llms_txt_absent",
            f"{cfg.origin}/llms.txt",
            evidence or "checked",
        )
    )


def _check_indexnow(cfg, skip_fetch: bool, emitted: list[F.Finding]) -> None:
    if cfg.build_path and cfg.build_path.is_dir():
        keys = list(cfg.build_path.glob("*.txt"))
        for key in keys:
            name = key.stem
            if len(name) >= 8 and all(c in "0123456789abcdefABCDEF" for c in name):
                return
        emitted.append(
            F.make(
                "ai.indexnow_key_missing",
                cfg.origin,
                f"no IndexNow key file found in {cfg.build_path}",
            )
        )


def _normalise(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        if stripped:
            lines.append(" ".join(stripped.split()).lower())
    return "\n".join(lines)


def _diff_summary(repo_text: str, live_text: str, repo_path: Path | None) -> str:
    repo_lines = set(_normalise(repo_text).splitlines())
    live_lines = set(_normalise(live_text).splitlines())
    added = sorted(live_lines - repo_lines)
    removed = sorted(repo_lines - live_lines)
    parts = [f"served robots.txt differs from {repo_path}"]
    if added:
        parts.append("served but not in repo: " + "; ".join(added[:5]))
    if removed:
        parts.append("in repo but not served: " + "; ".join(removed[:5]))
    return ". ".join(parts)


def _serialise(result: BotResult) -> dict:
    return {
        "token": result.bot.token,
        "operator": result.bot.operator,
        "purpose": result.bot.purpose,
        "docs": result.bot.docs,
        "intended": result.intended,
        "robots_allowed": result.robots_allowed,
        "robots_rule": result.robots_rule,
        "fetch_tested": result.fetch_tested,
        "fetch_statuses": result.fetch_statuses,
        "effective_allowed": result.effective_allowed,
        "matches_policy": result.matches_policy,
        "note": result.bot.note,
    }


def render(result: dict) -> str:
    lines = [
        f"AI crawler matrix for {result['site']}",
        f"robots.txt source: {result['robots_source']}",
        "",
        f"{'crawler':22s} {'operator':12s} {'purpose':11s} {'want':6s} "
        f"{'robots':8s} {'fetch':10s} {'verdict':8s}",
        "-" * 84,
    ]
    for bot in result["bots"]:
        if not bot["fetch_tested"]:
            fetch = "not run"
        else:
            statuses = set(bot["fetch_statuses"].values())
            fetch = "all 200" if statuses == {200} else ",".join(str(s) for s in sorted(statuses))
        verdict = "ok" if bot["matches_policy"] else "MISMATCH"
        lines.append(
            f"{bot['token']:22s} {bot['operator'][:12]:12s} {bot['purpose']:11s} "
            f"{bot['intended']:6s} {'allow' if bot['robots_allowed'] else 'BLOCK':8s} "
            f"{fetch:10s} {verdict:8s}"
        )
    lines.append("")
    for note in result["notes"]:
        lines.append(f"Note: {note}")
    if result["findings"]:
        lines.append("")
        lines.append(f"{len(result['findings'])} findings:")
        for finding in result["findings"]:
            lines.append(f"  [{finding['severity']}] {finding['id']}: {finding['evidence']}")
    return "\n".join(lines)


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Module E: AI crawler access matrix")
    parser.add_argument("--live", action="store_true", help="sample live URLs, not build output")
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="evaluate robots.txt only, make no network requests (used by the gate)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = run(cfg, live=args.live, skip_fetch=args.skip_fetch)
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

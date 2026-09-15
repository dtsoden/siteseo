"""Module O: agent readiness.

Checks whether AI agents, as opposed to search engines, can find, read,
authenticate to and pay a site, and places it on the 0 to 5 ladder Cloudflare's
scanner publishes. The level is reported in its own section. It is never folded
into search health or AI access, and every finding here carries `score: none`.

Three rules shape the code:

  1. Check the spec, not the scanner. Where isitagentready.com lags a spec, the
     check follows the spec and the difference is written down in
     reference/agent-readiness.md.
  2. An unmeasured check is not a passing check. Build output has no response
     headers, so Link headers and Markdown negotiation are unmeasured there, and
     a level that depends on them is reported as a ceiling with the reason.
  3. The profile in siteseo.yaml decides which absences are findings. A content
     site is never told to build an OAuth server. A published document that is
     broken is reported whatever the profile, because it is broken for anyone
     who reads it.

None of this affects Google Search. Google's AI optimization guide says Search
ignores Markdown, AI text files and special markup.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import yaml
from selectolax.parser import HTMLParser

import findings as F
import robots_check
from source import DEFAULT_UA, LiveSource, OfflineRefused, Response, Source, open_source

PASS, FAIL, NEUTRAL = "pass", "fail", "neutral"
#: The check exists for this profile but cannot be measured from this source.
UNMEASURED = "unmeasured"
#: The check is outside this site's profile and was not run.
SKIPPED = "skipped"
#: Statuses that could still turn out to be a pass.
UNKNOWN = {UNMEASURED, SKIPPED}

LEVEL_ONE = ("robots_txt", "sitemap", "link_headers")
INTEGRATIONS = ("mcp_card", "a2a_card", "agent_skills", "api_catalog")
AUTH_METADATA = ("oauth_discovery", "protected_resource", "auth_md")
COMMERCE = ("acp", "ucp", "mpp", "x402", "ap2")

#: Link relations that point an agent at something machine-readable. Cloudflare's
#: scanner counted these on the sites scanned; rel="sitemap" it did not.
AGENT_RELS = {
    "api-catalog", "service-desc", "service-doc", "service-meta",
    "describedby", "alternate", "ard", "ai-catalog",
}

#: Tokens that appear in old robots.txt files but that the operator no longer
#: documents, with the tokens that replaced them.
OBSOLETE_TOKENS = {
    "anthropic-ai": ("ClaudeBot", "Claude-SearchBot", "Claude-User"),
    "claude-web": ("ClaudeBot", "Claude-SearchBot", "Claude-User"),
}

SIGNAL_KEYS = {"search": "search", "ai-input": "ai_input", "ai-train": "ai_train"}
#: Cloudflare's managed robots.txt writes use=reference. Its docs call the
#: category experimental, so it is recognised rather than reported as invalid.
EXPERIMENTAL_SIGNAL_KEYS = {"use"}

SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKILL_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SKILLS_SCHEMA = "https://schemas.agentskills.io/discovery/0.2.0/schema.json"
MAX_SKILLS_VERIFIED = 20

A2A_REQUIRED = (
    "name", "description", "version", "supportedInterfaces", "capabilities",
    "defaultInputModes", "defaultOutputModes", "skills",
)
A2A_SKILL_REQUIRED = ("id", "name", "description", "tags")
AUTH_MD_STALE = ("register_uri", "claim_uri", "verified_email")

DOH_RESOLVER = "https://cloudflare-dns.com/dns-query"
DNS_AID_NAMES = ("_index._agents", "_a2a._agents", "_mcp._agents")
SVCB, HTTPS_RR = 64, 65

MAX_SCRIPTS = 8
MAX_SCRIPT_BYTES = 1024 * 1024
MODEL_CONTEXT = re.compile(r"\b(document|navigator)\s*\.\s*modelContext\b")
REGISTER_TOOL = re.compile(r"\bregisterTool\s*\(")
DECLARATIVE_TOOL = re.compile(r"<form\b[^>]*\btoolname\s*=", re.I)

GOOGLE_NOTE = (
    "Agent readiness does not affect Google Search. Google's AI optimization guide "
    "says Search ignores Markdown, AI text files and special markup."
)


def reference() -> dict:
    path = F.plugin_root() / "skills" / "siteseo" / "reference" / "agent-readiness.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _standards() -> dict[str, dict]:
    return {row["check"]: row for row in reference().get("standards", [])}


def _level_names() -> dict[int, str]:
    return {row["level"]: row["name"] for row in reference().get("levels", [])}


def _require_network() -> None:
    if os.environ.get("SITESEO_OFFLINE"):
        raise OfflineRefused("SITESEO_OFFLINE is set, so no network request may be made.")


# ---------------------------------------------------------------------------
# Fetching


@dataclass
class Doc:
    """One well-known document, as fetched."""

    url: str
    status: int
    found: bool
    data: Any = None
    text: str = ""
    error: str | None = None
    content_type: str | None = None
    note: str = ""


def _looks_like_html(text: str, content_type: str | None) -> bool:
    if content_type and "html" in content_type.lower():
        return True
    head = text.lstrip()[:20].lower()
    return head.startswith(("<!doctype html", "<html"))


class Probe:
    """Fetches through one Source, once per path and Accept value."""

    def __init__(self, cfg, *, live: bool):
        self.cfg = cfg
        self.src: Source = open_source(cfg, live=live)
        self.live = isinstance(self.src, LiveSource)
        self._cache: dict[tuple[str, str | None], Response] = {}

    def get(self, path: str, accept: str | None = None) -> Response:
        key = (path, accept)
        if key not in self._cache:
            headers = {"Accept": accept} if accept else None
            self._cache[key] = self.src.fetch(path, headers=headers)
        return self._cache[key]

    def document(self, path: str, accept: str | None = None, *, as_json: bool = True) -> Doc:
        resp = self.get(path, accept)
        url = self.src.absolute(path)
        ctype = resp.headers.get("content-type") if resp.headers_available else None
        if not (200 <= resp.status < 300) or not resp.body:
            reason = resp.error or f"returned {resp.status}"
            return Doc(url, resp.status, False, note=reason)
        text = resp.text()
        if _looks_like_html(text, ctype) and not path.endswith((".html", "/")):
            return Doc(
                url, resp.status, False, content_type=ctype,
                note="returned an HTML page, most likely the host's catch-all route",
            )
        if not as_json:
            return Doc(url, resp.status, True, text=text, content_type=ctype)
        try:
            data = json.loads(text)
        except ValueError as exc:
            return Doc(url, resp.status, True, text=text, content_type=ctype,
                       error=f"not valid JSON ({exc})")
        return Doc(url, resp.status, True, data=data, text=text, content_type=ctype)

    def close(self) -> None:
        self.src.close()


# ---------------------------------------------------------------------------
# The run


@dataclass
class Check:
    name: str
    label: str
    status: str
    summary: str
    url: str = ""
    profile: str = "content"

    def to_dict(self) -> dict:
        return {
            "check": self.name, "label": self.label, "status": self.status,
            "summary": self.summary, "url": self.url, "profile": self.profile,
        }


@dataclass
class Run:
    cfg: Any
    probe: Probe
    checks: dict[str, Check] = field(default_factory=dict)
    emitted: list[F.Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    standards: dict[str, dict] = field(default_factory=_standards)
    robots: robots_check.Robots | None = None
    robots_text: str = ""

    def covers(self, name: str) -> bool:
        profile = self.standards.get(name, {}).get("profile", "content")
        return self.cfg.agent_readiness.covers(profile)

    def record(self, name: str, status: str, summary: str, url: str = "") -> None:
        meta = self.standards.get(name, {})
        self.checks[name] = Check(
            name=name, label=meta.get("name", name), status=status, summary=summary,
            url=url, profile=meta.get("profile", "content"),
        )

    def emit(self, check_id: str, url: str, evidence: str, **kwargs) -> None:
        self.emitted.append(F.make(check_id, url, evidence, **kwargs))

    def missing(self, name: str, check_id: str, url: str, evidence: str) -> None:
        """Report an absence, but only when the standard fits this profile."""
        if self.covers(name):
            self.emit(check_id, url, evidence)

    def status(self, name: str) -> str:
        check = self.checks.get(name)
        return check.status if check else SKIPPED

    def passed(self, name: str) -> bool:
        return self.status(name) == PASS


def run(cfg, *, live: bool = False) -> dict:
    """Evaluate every agent readiness check. Returns a JSON-serialisable result."""
    probe = Probe(cfg, live=live)
    state = Run(cfg=cfg, probe=probe)
    try:
        check_robots(state)
        check_sitemap(state)
        check_ai_rules(state)
        check_content_signals(state)
        check_markdown(state)
        check_api_catalog(state)
        check_mcp_card(state)
        check_a2a_card(state)
        check_agent_skills(state)
        check_web_bot_auth(state)
        check_link_headers(state)

        if cfg.agent_readiness.covers("api"):
            check_oauth_discovery(state)
            check_protected_resource(state)
            check_auth_md(state)
            check_webmcp(state)
            check_dns_aid(state)
            check_ard(state)
        else:
            for name in ("oauth_discovery", "protected_resource", "auth_md", "webmcp",
                         "dns_aid", "ard"):
                state.record(name, SKIPPED, "not checked for a content profile")

        if cfg.agent_readiness.covers("commerce"):
            check_commerce(state)
        else:
            for name in COMMERCE:
                state.record(name, SKIPPED, "not checked unless the profile is commerce")
    finally:
        probe.close()

    level, ceiling = compute_level(state)
    names = _level_names()
    source_kind = "live" if probe.live else "build"
    if not probe.live:
        state.notes.append(
            "Audited build output, which has no response headers. Link headers and "
            "Markdown negotiation are unmeasured; run with --live to measure them."
        )
    state.notes.append(GOOGLE_NOTE)

    merged = F.order(F.merge(state.emitted))
    return {
        "module": "O",
        "site": cfg.site,
        "profile": cfg.agent_readiness.profile,
        "source_kind": source_kind,
        "level": level,
        "level_name": names.get(level, ""),
        "ceiling": ceiling,
        "next_level": next_level(state, level, names),
        "checks": [check.to_dict() for check in state.checks.values()],
        "findings": [f.to_dict() for f in merged],
        "notes": state.notes,
    }


# ---------------------------------------------------------------------------
# Level


def compute_level(state: Run) -> tuple[int, str | None]:
    """Place the site on the published ladder.

    Returns the level and, when a check that was not measured could have lifted
    it, the reason. Cloudflare's scanner counts a check left out of a scan as
    satisfied. siteseo reports a ceiling instead.
    """
    def unknown(names) -> list[str]:
        return [n for n in names if state.status(n) in UNKNOWN]

    def ceiling(names) -> str | None:
        pending = unknown(names)
        if not pending:
            return None
        return "could be higher: " + ", ".join(
            f"{state.checks[n].label if n in state.checks else n} "
            f"({state.status(n)})" for n in pending
        )

    passed = sum(state.passed(n) for n in LEVEL_ONE)
    if passed < 2:
        pending = unknown(LEVEL_ONE)
        return 0, ceiling(LEVEL_ONE) if passed + len(pending) >= 2 else None

    for level, needs in ((2, ("ai_rules", "content_signals")), (3, ("markdown_negotiation",))):
        failing = [n for n in needs if not state.passed(n)]
        if failing:
            return level - 1, ceiling(failing)

    if not any(state.passed(n) for n in INTEGRATIONS):
        return 3, ceiling(INTEGRATIONS)

    groups = {
        "web_bot_auth": state.passed("web_bot_auth"),
        "integrations": all(state.passed(n) for n in INTEGRATIONS),
        "auth": any(state.passed(n) for n in AUTH_METADATA),
    }
    if sum(groups.values()) >= 2:
        return 5, None
    pending = unknown(("web_bot_auth", *INTEGRATIONS, *AUTH_METADATA))
    return 4, ceiling(pending) if pending else None


def next_level(state: Run, level: int, names: dict[int, str]) -> dict | None:
    """What the next rung asks for, named by check."""
    if level >= 5:
        return None
    if level == 0:
        needs = [n for n in LEVEL_ONE if not state.passed(n)]
        rule = "two of these three"
    elif level == 1:
        needs = [n for n in ("ai_rules", "content_signals") if not state.passed(n)]
        rule = "all of these"
    elif level == 2:
        needs = ["markdown_negotiation"]
        rule = "this"
    elif level == 3:
        needs = list(INTEGRATIONS)
        rule = "one of these"
    else:
        needs = ["web_bot_auth", *[n for n in INTEGRATIONS if not state.passed(n)],
                 *AUTH_METADATA]
        rule = "two of: Web Bot Auth, all four integration documents, auth metadata"
    return {
        "level": level + 1,
        "name": names.get(level + 1, ""),
        "rule": rule,
        "needs": [state.checks[n].label if n in state.checks else n for n in needs],
    }


# ---------------------------------------------------------------------------
# Level 1 and 2: robots.txt, sitemap, AI rules, Content Signals


def check_robots(state: Run) -> None:
    resp = state.probe.get("/robots.txt")
    url = state.probe.src.absolute("/robots.txt")
    if resp.status >= 500:
        state.record("robots_txt", FAIL, f"served {resp.status}; module A reports it", url)
        return
    if resp.status != 200:
        state.record("robots_txt", FAIL, f"returned {resp.status or resp.error}", url)
        state.missing("robots_txt", "agent.robots_txt_missing", url,
                      f"/robots.txt returned {resp.status or resp.error}")
        return

    text = resp.text()
    state.robots_text = text
    state.robots = robots_check.parse(text, fetch_status=200)
    if not state.robots.groups:
        state.record("robots_txt", FAIL, "present but declares no User-agent group", url)
        return

    summary = f"{len(state.robots.groups)} User-agent group(s)"
    ctype = resp.headers.get("content-type", "") if resp.headers_available else ""
    if ctype and "text/plain" not in ctype.lower():
        summary += f", served as {ctype} rather than text/plain"
    state.record("robots_txt", PASS, summary, url)


def check_sitemap(state: Run) -> None:
    listed = state.robots.sitemaps if state.robots else []
    target = "/sitemap.xml"
    origin = state.probe.src.absolute("/")
    for line in listed:
        if urlparse(line).netloc == urlparse(origin).netloc:
            target = urlparse(line).path or "/sitemap.xml"
            break

    resp = state.probe.get(target)
    url = state.probe.src.absolute(target)
    if resp.status != 200 or not resp.body:
        state.record("sitemap", FAIL,
                     f"{target} returned {resp.status or resp.error}; module A reports it", url)
        return

    body = resp.body
    if body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except OSError:
            state.record("sitemap", FAIL, "gzip sitemap could not be decompressed", url)
            return
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        state.record("sitemap", FAIL, f"not well-formed XML ({exc}); module A reports it", url)
        return

    tag = root.tag.rsplit("}", 1)[-1]
    if tag not in {"urlset", "sitemapindex"}:
        state.record("sitemap", FAIL, f"root element is <{tag}>, not urlset or sitemapindex", url)
        return
    how = "named in robots.txt" if listed else "found at /sitemap.xml"
    state.record("sitemap", PASS, f"valid {tag}, {how}", url)


def check_ai_rules(state: Run) -> None:
    url = state.probe.src.absolute("/robots.txt")
    if state.robots is None or not state.robots.groups:
        state.record("ai_rules", FAIL, "no robots.txt groups to evaluate", url)
        return

    import ai_matrix

    current = {bot.token.lower(): bot.token for bot in ai_matrix.load_bots()}
    named = {agent.lower() for group in state.robots.groups for agent in group.agents}
    explicit = sorted(current[token] for token in named if token in current)
    wildcard = "*" in named

    if explicit:
        summary = "explicit groups for " + ", ".join(explicit[:6])
        if len(explicit) > 6:
            summary += f" and {len(explicit) - 6} more"
    elif wildcard:
        summary = "no AI-specific groups; the * group applies to every AI crawler"
    else:
        summary = "no group names an AI crawler, so they fall back to no restriction"
    state.record("ai_rules", PASS, summary, url)

    obsolete = sorted(token for token in named if token in OBSOLETE_TOKENS)
    if obsolete:
        replacements = {r.lower() for token in obsolete for r in OBSOLETE_TOKENS[token]}
        if not replacements & named:
            state.emit(
                "agent.ai_rules_obsolete_token", url,
                "robots.txt has groups for " + ", ".join(obsolete) + " but none for "
                + ", ".join(sorted(OBSOLETE_TOKENS[obsolete[0]]))
                + ". Rules written for the old tokens do not reach the current crawlers.",
            )


@dataclass
class SignalLine:
    line_number: int
    agents: list[str]
    path: str
    pairs: dict[str, str]
    raw: str


def parse_signals(text: str, directive: str = "content-signal") -> list[SignalLine]:
    """Content-Signal (or Content-Usage) lines, with the group each belongs to.

    robots_check ignores directives outside RFC 9309, which is correct for access
    decisions, so the group tracking is repeated here for this one directive.
    """
    lines: list[SignalLine] = []
    agents: list[str] = []
    accepting = False
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        name, value = (part.strip() for part in line.split(":", 1))
        name = name.lower()
        if name == "user-agent":
            if not accepting:
                agents = []
                accepting = True
            agents.append(value)
            continue
        if name in {"allow", "disallow"}:
            accepting = False
            continue
        if name != directive:
            continue
        accepting = False
        path = ""
        if value.startswith("/"):
            path, _, value = value.partition(" ")
        pairs: dict[str, str] = {}
        for item in value.split(","):
            if not item.strip():
                continue
            key, _, setting = item.partition("=")
            pairs[key.strip().lower()] = setting.strip().lower()
        lines.append(SignalLine(number, list(agents) or ["*"], path, pairs, raw.strip()))
    return lines


def signal_line(cfg) -> str:
    """The Content-Signal line this site's policy implies."""
    wanted = cfg.content_signals()
    return "Content-Signal: " + ", ".join(
        f"{key}={'yes' if wanted[attr] else 'no'}" for key, attr in SIGNAL_KEYS.items()
    )


def check_content_signals(state: Run) -> None:
    url = state.probe.src.absolute("/robots.txt")
    if state.robots is None:
        state.record("content_signals", FAIL, "no robots.txt to carry them", url)
        return

    lines = parse_signals(state.robots_text)
    usage = parse_signals(state.robots_text, "content-usage")
    if usage:
        state.notes.append(
            f"robots.txt carries {len(usage)} Content-Usage line(s), the IETF AI "
            "preferences draft form. Recorded; that draft has no consensus yet."
        )

    if not lines:
        state.record("content_signals", FAIL, "no Content-Signal line in robots.txt", url)
        state.missing(
            "content_signals", "agent.content_signals_missing", url,
            f"robots.txt has no Content-Signal line. From ai_policy: {signal_line(state.cfg)}",
        )
        return

    problems: list[str] = []
    valid = 0
    for line in lines:
        for key, value in line.pairs.items():
            if key in EXPERIMENTAL_SIGNAL_KEYS:
                continue
            if key not in SIGNAL_KEYS:
                problems.append(f"line {line.line_number}: unknown category {key!r}")
            elif value not in {"yes", "no"}:
                problems.append(f"line {line.line_number}: {key}={value!r} is not yes or no")
            else:
                valid += 1
    if problems:
        state.emit("agent.content_signals_invalid", url, "; ".join(problems[:5]))

    if not valid:
        state.record("content_signals", FAIL, "Content-Signal present but nothing valid in it", url)
        return

    # Compare the site-wide line, the one in the * group with no path, against
    # what siteseo.yaml says the site means.
    wanted = state.cfg.content_signals()
    sitewide = [ln for ln in lines if "*" in ln.agents and not ln.path]
    contradictions = []
    for line in sitewide:
        for key, attr in SIGNAL_KEYS.items():
            value = line.pairs.get(key)
            if value not in {"yes", "no"}:
                continue
            if (value == "yes") != wanted[attr]:
                source = (
                    "agent_readiness.content_signals" if attr in state.cfg.agent_readiness.content_signals
                    else ("ai_policy.training" if attr == "ai_train" else "ai_policy.search_and_user_fetch")
                )
                contradictions.append(
                    f"{key}={value} on line {line.line_number}, but {source} means "
                    f"{key}={'yes' if wanted[attr] else 'no'}"
                )
    if contradictions:
        state.emit("agent.content_signals_contradict_policy", url, "; ".join(contradictions))

    summary = "; ".join(ln.raw for ln in lines[:2])
    state.record("content_signals", PASS, summary, url)


# ---------------------------------------------------------------------------
# Level 3: Markdown negotiation


def check_markdown(state: Run) -> None:
    home = state.probe.src.absolute("/")
    if not state.probe.live:
        state.record("markdown_negotiation", UNMEASURED,
                     "needs a live server to negotiate with", home)
        return

    resp = state.probe.get("/", "text/markdown")
    ctype = resp.headers.get("content-type", "")
    if resp.status != 200 or "text/markdown" not in ctype.lower():
        state.record(
            "markdown_negotiation", FAIL,
            f"Accept: text/markdown got {resp.status} {ctype or 'no content type'}", home,
        )
        state.missing(
            "markdown_negotiation", "agent.markdown_negotiation_missing", home,
            f"GET / with Accept: text/markdown returned {resp.status} as "
            f"{ctype or 'no content type'}",
        )
        return

    vary = resp.headers.get("vary", "")
    if "accept" not in {part.strip().lower() for part in vary.split(",")} and vary.strip() != "*":
        state.emit(
            "agent.markdown_missing_vary", home,
            f"Markdown served for Accept: text/markdown with Vary: {vary or '(absent)'}",
        )
    tokens = resp.headers.get("x-markdown-tokens")
    summary = f"served {ctype}" + (f", {tokens} tokens" if tokens else "")
    state.record("markdown_negotiation", PASS, summary, home)


# ---------------------------------------------------------------------------
# Level 1 again: Link headers, evaluated last so it knows what exists to link to


def parse_link_header(value: str) -> list[tuple[str, set[str]]]:
    """RFC 8288 Link values as (target, relations)."""
    links = []
    for match in re.finditer(r"<([^>]*)>\s*((?:;\s*[^,;]+)*)", value or ""):
        rels: set[str] = set()
        for param in match.group(2).split(";"):
            name, _, raw = param.strip().partition("=")
            if name.strip().lower() == "rel":
                rels.update(raw.strip().strip('"').lower().split())
        links.append((match.group(1), rels))
    return links


def _headers_file_links(state: Run) -> str | None:
    """Link headers a Netlify or Cloudflare Pages _headers file sets on /."""
    build = state.cfg.build_path
    if not build or not (build / "_headers").is_file():
        return None
    values: list[str] = []
    applies = False
    for raw in (build / "_headers").read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace():
            applies = raw.strip() in {"/", "/*"}
            continue
        if applies:
            name, _, value = raw.strip().partition(":")
            if name.strip().lower() == "link":
                values.append(value.strip())
    return ", ".join(values)


def check_link_headers(state: Run) -> None:
    home = state.probe.src.absolute("/")
    if state.probe.live:
        value = state.probe.get("/").headers.get("link", "")
        where = "homepage response"
    else:
        value = _headers_file_links(state)
        if value is None:
            state.record("link_headers", UNMEASURED,
                         "no server headers in build output and no _headers file", home)
            return
        where = "_headers file"

    rels = {rel for _, found in parse_link_header(value) for rel in found}
    useful = sorted(rels & AGENT_RELS)
    if useful:
        state.record("link_headers", PASS, f"{where} links rel " + ", ".join(useful), home)
        return

    state.record("link_headers", FAIL, f"{where} has no Link to an agent resource", home)
    published = [state.checks[n].label for n in INTEGRATIONS if state.passed(n)]
    if published or state.cfg.agent_readiness.covers("api"):
        target = (
            f"{', '.join(published)} exist but nothing points to them"
            if published else "nothing points agents at machine-readable resources"
        )
        state.emit("agent.link_headers_missing", home,
                   f"{where} sends no agent Link relation; {target}")


# ---------------------------------------------------------------------------
# Level 4: the integration documents


def check_api_catalog(state: Run) -> None:
    doc = state.probe.document("/.well-known/api-catalog",
                               "application/linkset+json, application/json")
    if not doc.found:
        state.record("api_catalog", FAIL, doc.note, doc.url)
        state.missing("api_catalog", "agent.api_catalog_missing", doc.url,
                      f"/.well-known/api-catalog {doc.note}")
        return
    if doc.error:
        state.record("api_catalog", FAIL, doc.error, doc.url)
        state.emit("agent.api_catalog_invalid", doc.url, doc.error)
        return

    linkset = doc.data.get("linkset") if isinstance(doc.data, dict) else None
    if not isinstance(linkset, list) or not linkset:
        state.record("api_catalog", FAIL, "no linkset array", doc.url)
        state.emit("agent.api_catalog_invalid", doc.url, "JSON has no non-empty linkset array")
        return

    no_anchor = sum(1 for entry in linkset if not isinstance(entry, dict) or "anchor" not in entry)
    if no_anchor:
        state.emit("agent.api_catalog_invalid", doc.url,
                   f"{no_anchor} of {len(linkset)} linkset entries have no anchor")
    if doc.content_type and "application/linkset+json" not in doc.content_type.lower():
        state.emit("agent.api_catalog_invalid", doc.url,
                   f"served as {doc.content_type}, not application/linkset+json",
                   severity="notice")
    state.record("api_catalog", PASS, f"{len(linkset)} linkset entries", doc.url)


MCP_CARD_PATHS = (
    "/.well-known/mcp/server-card.json",
    "/.well-known/mcp/server-cards.json",
    "/.well-known/mcp.json",
)


def check_mcp_card(state: Run) -> None:
    first_url = state.probe.src.absolute(MCP_CARD_PATHS[0])
    for path in MCP_CARD_PATHS:
        doc = state.probe.document(path)
        if not doc.found:
            continue
        if doc.error:
            state.record("mcp_card", FAIL, doc.error, doc.url)
            state.emit("agent.mcp_card_invalid", doc.url, doc.error)
            return

        card = doc.data[0] if isinstance(doc.data, list) and doc.data else doc.data
        if not isinstance(card, dict):
            state.record("mcp_card", FAIL, "not a JSON object", doc.url)
            state.emit("agent.mcp_card_invalid", doc.url, "card is not a JSON object")
            return

        info = card.get("serverInfo") if isinstance(card.get("serverInfo"), dict) else None
        name = (info or card).get("name")
        version = (info or card).get("version")
        if not name or not version:
            state.record("mcp_card", FAIL, "no name and version", doc.url)
            state.emit("agent.mcp_card_invalid", doc.url,
                       f"{path} has no {'name' if not name else 'version'}")
            return
        if info is not None:
            state.emit("agent.mcp_card_legacy_shape", doc.url,
                       f"{path} uses serverInfo.name and serverInfo.version (SEP-1649 shape)")
        state.record("mcp_card", PASS, f"{name} {version} at {path}", doc.url)
        return

    state.record("mcp_card", FAIL, "no card at any known location", first_url)
    state.missing("mcp_card", "agent.mcp_card_missing", first_url,
                  "no MCP server card at " + ", ".join(MCP_CARD_PATHS))


def check_a2a_card(state: Run) -> None:
    doc = state.probe.document("/.well-known/agent-card.json")
    legacy_path = False
    if not doc.found:
        older = state.probe.document("/.well-known/agent.json")
        if older.found:
            doc, legacy_path = older, True
    if not doc.found:
        state.record("a2a_card", FAIL, doc.note, doc.url)
        state.missing("a2a_card", "agent.a2a_card_missing", doc.url,
                      f"/.well-known/agent-card.json {doc.note}")
        return
    if doc.error or not isinstance(doc.data, dict):
        reason = doc.error or "card is not a JSON object"
        state.record("a2a_card", FAIL, reason, doc.url)
        state.emit("agent.a2a_card_invalid", doc.url, reason)
        return

    card = doc.data
    legacy_fields = [k for k in ("url", "preferredTransport", "additionalInterfaces") if k in card]
    if legacy_path or (legacy_fields and "supportedInterfaces" not in card):
        where = "/.well-known/agent.json" if legacy_path else "the card"
        detail = f"top-level {', '.join(legacy_fields)}" if legacy_fields else "the pre-1.0 path"
        state.emit("agent.a2a_card_legacy_shape", doc.url, f"{where} uses {detail}")

    required = [k for k in A2A_REQUIRED if k not in card]
    if "supportedInterfaces" in required and legacy_fields:
        required.remove("supportedInterfaces")
    skills = card.get("skills") if isinstance(card.get("skills"), list) else []
    incomplete = [
        str(skill.get("id", i)) for i, skill in enumerate(skills)
        if not isinstance(skill, dict) or any(k not in skill for k in A2A_SKILL_REQUIRED)
    ]
    if required or incomplete:
        parts = []
        if required:
            parts.append("missing " + ", ".join(required))
        if incomplete:
            parts.append(f"{len(incomplete)} skill(s) lack id, name, description or tags")
        state.emit("agent.a2a_card_invalid", doc.url, "; ".join(parts))

    if not card.get("name") or not (card.get("supportedInterfaces") or card.get("url")):
        state.record("a2a_card", FAIL, "no name or endpoint", doc.url)
        return
    state.record("a2a_card", PASS, f"{card.get('name')}, {len(skills)} skill(s)", doc.url)
    state.a2a_card = card  # type: ignore[attr-defined]


def check_agent_skills(state: Run) -> None:
    doc = state.probe.document("/.well-known/agent-skills/index.json")
    if not doc.found:
        older = state.probe.document("/.well-known/skills/index.json")
        if older.found:
            doc = older
            state.notes.append(
                "skills index found at /.well-known/skills/, the 0.1 location. "
                "Discovery 0.2.0 moved it to /.well-known/agent-skills/."
            )
    if not doc.found:
        state.record("agent_skills", FAIL, doc.note, doc.url)
        state.missing("agent_skills", "agent.skills_index_missing", doc.url,
                      f"/.well-known/agent-skills/index.json {doc.note}")
        return
    if doc.error or not isinstance(doc.data, dict):
        reason = doc.error or "index is not a JSON object"
        state.record("agent_skills", FAIL, reason, doc.url)
        state.emit("agent.skills_index_invalid", doc.url, reason)
        return

    skills = doc.data.get("skills")
    if not isinstance(skills, list) or not skills:
        state.record("agent_skills", FAIL, "no skills array", doc.url)
        state.emit("agent.skills_index_invalid", doc.url, "index has no non-empty skills array")
        return

    problems: list[str] = []
    if doc.data.get("$schema") != SKILLS_SCHEMA:
        problems.append(f"$schema is {doc.data.get('$schema')!r}, not the 0.2.0 schema URL")
    valid: list[dict] = []
    for i, entry in enumerate(skills):
        label = entry.get("name", f"entry {i}") if isinstance(entry, dict) else f"entry {i}"
        issues = _skill_entry_problems(entry)
        if issues:
            problems.append(f"{label}: {', '.join(issues)}")
        else:
            valid.append(entry)
    if problems:
        state.emit("agent.skills_index_invalid", doc.url, "; ".join(problems[:5]))

    mismatched = []
    for entry in valid[:MAX_SKILLS_VERIFIED]:
        target = urljoin(doc.url, entry["url"])
        resp = state.probe.get(target)
        if resp.status != 200:
            mismatched.append(f"{entry['name']}: {entry['url']} returned {resp.status}")
            continue
        actual = "sha256:" + hashlib.sha256(resp.body).hexdigest()
        if actual != entry["digest"]:
            mismatched.append(f"{entry['name']}: index says {entry['digest'][:19]}, file is {actual[:19]}")
    if mismatched:
        state.emit("agent.skills_digest_mismatch", doc.url, "; ".join(mismatched[:5]))

    if not valid:
        state.record("agent_skills", FAIL, "no valid entries", doc.url)
        return
    state.record("agent_skills", PASS, f"{len(valid)} of {len(skills)} entries valid", doc.url)


def _skill_entry_problems(entry: Any) -> list[str]:
    if not isinstance(entry, dict):
        return ["not an object"]
    issues = []
    name = entry.get("name")
    if not isinstance(name, str) or len(name) > 64 or not SKILL_NAME.match(name):
        issues.append("name must be 1-64 lowercase letters, digits and hyphens")
    if entry.get("type") not in {"skill-md", "archive"}:
        issues.append("type must be skill-md or archive")
    description = entry.get("description")
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        issues.append("description must be 1-1024 characters")
    if not isinstance(entry.get("url"), str) or not entry.get("url"):
        issues.append("url is missing")
    if not isinstance(entry.get("digest"), str) or not SKILL_DIGEST.match(entry["digest"]):
        issues.append("digest must be sha256: and 64 lowercase hex characters")
    return issues


# ---------------------------------------------------------------------------
# Level 5: Web Bot Auth and auth metadata


def check_web_bot_auth(state: Run) -> None:
    doc = state.probe.document("/.well-known/http-message-signatures-directory",
                               "application/http-message-signatures-directory+json")
    if not doc.found:
        state.record("web_bot_auth", NEUTRAL,
                     "no key directory; only sites that run their own bot need one", doc.url)
        return
    keys = doc.data.get("keys") if isinstance(doc.data, dict) else None
    usable = [k for k in keys or [] if isinstance(k, dict) and k.get("kty")]
    if doc.error or not usable:
        reason = doc.error or "no keys array with a kty in any entry"
        state.record("web_bot_auth", FAIL, reason, doc.url)
        state.emit("agent.web_bot_auth_invalid", doc.url, reason)
        return
    state.record("web_bot_auth", PASS, f"{len(usable)} key(s)", doc.url)


def check_oauth_discovery(state: Run) -> None:
    for path, oidc in (("/.well-known/openid-configuration", True),
                       ("/.well-known/oauth-authorization-server", False)):
        doc = state.probe.document(path)
        if not doc.found:
            continue
        if doc.error or not isinstance(doc.data, dict):
            reason = doc.error or "not a JSON object"
            state.record("oauth_discovery", FAIL, reason, doc.url)
            state.emit("agent.oauth_discovery_invalid", doc.url, reason)
            return

        meta = doc.data
        required = ["issuer", "response_types_supported"]
        if oidc:
            required += ["authorization_endpoint", "jwks_uri"]
        missing = [k for k in required if not meta.get(k)]
        issuer = str(meta.get("issuer", ""))
        if issuer and not issuer.startswith("https://"):
            missing.append("an https issuer")
        if missing:
            state.emit("agent.oauth_discovery_invalid", doc.url, f"{path} lacks " + ", ".join(missing))
        recommended = [k for k in ("token_endpoint", "grant_types_supported") if not meta.get(k)]
        if recommended and not missing:
            state.emit("agent.oauth_discovery_invalid", doc.url,
                       f"{path} lacks {', '.join(recommended)}, which agents use to pick a grant",
                       severity="notice")
        _stale_auth_fields(state, doc.url, json.dumps(meta.get("agent_auth", {})))

        if not meta.get("issuer"):
            state.record("oauth_discovery", FAIL, "no issuer", doc.url)
            return
        state.record("oauth_discovery", PASS, f"issuer {issuer}", doc.url)
        return

    url = state.probe.src.absolute("/.well-known/oauth-authorization-server")
    state.record("oauth_discovery", FAIL, "neither discovery document found", url)
    state.missing("oauth_discovery", "agent.oauth_discovery_missing", url,
                  "no /.well-known/openid-configuration or /.well-known/oauth-authorization-server")


def check_protected_resource(state: Run) -> None:
    doc = state.probe.document("/.well-known/oauth-protected-resource")
    if not doc.found:
        state.record("protected_resource", FAIL, doc.note, doc.url)
        state.missing("protected_resource", "agent.protected_resource_missing", doc.url,
                      f"/.well-known/oauth-protected-resource {doc.note}")
        return
    if doc.error or not isinstance(doc.data, dict) or not doc.data.get("resource"):
        reason = doc.error or "no resource field"
        state.record("protected_resource", FAIL, reason, doc.url)
        state.emit("agent.protected_resource_invalid", doc.url, reason)
        return
    if not doc.data.get("authorization_servers"):
        state.emit("agent.protected_resource_invalid", doc.url,
                   "no authorization_servers, so an agent cannot tell where to get a token",
                   severity="notice")
    state.record("protected_resource", PASS, f"resource {doc.data['resource']}", doc.url)


def check_auth_md(state: Run) -> None:
    doc = state.probe.document("/auth.md", "text/markdown, text/plain", as_json=False)
    if not doc.found:
        state.record("auth_md", FAIL, doc.note, doc.url)
        state.missing("auth_md", "agent.auth_md_missing", doc.url, f"/auth.md {doc.note}")
        return
    heading = next(
        (line[2:].strip() for line in doc.text.splitlines() if line.startswith("# ")), ""
    )
    _stale_auth_fields(state, doc.url, doc.text)
    if "auth.md" not in heading.lower():
        state.record("auth_md", FAIL, f"H1 is {heading!r}", doc.url)
        state.emit("agent.auth_md_invalid", doc.url,
                   f"first H1 is {heading!r}, which does not contain auth.md")
        return
    state.record("auth_md", PASS, f"H1 {heading!r}", doc.url)


def _stale_auth_fields(state: Run, url: str, text: str) -> None:
    stale = [name for name in AUTH_MD_STALE if name in text]
    if stale:
        state.emit("agent.auth_md_stale_fields", url, "uses " + ", ".join(stale))


# ---------------------------------------------------------------------------
# Outside the ladder: WebMCP, DNS-AID, ARD


def check_webmcp(state: Run) -> None:
    home = state.probe.src.absolute("/")
    resp = state.probe.get("/")
    if resp.status != 200:
        state.record("webmcp", FAIL, f"homepage returned {resp.status}", home)
        return

    html = resp.text()
    sources = [html]
    tree = HTMLParser(html)
    origin = urlparse(home).netloc
    fetched = 0
    for node in tree.css("script"):
        src = node.attributes.get("src")
        if not src:
            continue
        target = urljoin(home, src)
        if urlparse(target).netloc != origin or fetched >= MAX_SCRIPTS:
            continue
        script = state.probe.get(target)
        fetched += 1
        if script.status == 200 and len(script.body) <= MAX_SCRIPT_BYTES:
            sources.append(script.text())

    text = "\n".join(sources)
    used = {match.group(1) for match in MODEL_CONTEXT.finditer(text)}
    imperative = bool(used) and bool(REGISTER_TOOL.search(text))
    declarative = bool(DECLARATIVE_TOOL.search(html))

    if "navigator" in used and "document" not in used:
        state.emit("agent.webmcp_legacy_api", home,
                   "page scripts call navigator.modelContext and never document.modelContext")
    if imperative or declarative:
        how = " and ".join(
            label for label, hit in (("registerTool", imperative), ("toolname forms", declarative))
            if hit
        )
        state.record("webmcp", PASS,
                     f"{how} found by reading the page and {fetched} script(s); not run in a browser",
                     home)
        return
    state.record("webmcp", FAIL, f"no tool registration in the page or {fetched} script(s)", home)
    state.missing("webmcp", "agent.webmcp_not_detected", home,
                  f"no modelContext.registerTool call or toolname form in the homepage "
                  f"or {fetched} same-origin script(s). Read statically, not in a browser.")


def check_dns_aid(state: Run) -> None:
    host = urlparse(state.cfg.site).hostname or ""
    if not state.probe.live or os.environ.get("SITESEO_OFFLINE"):
        state.record("dns_aid", UNMEASURED, "DNS lookups run only against a live site", host)
        return

    found: list[str] = []
    validated = False
    try:
        _require_network()
        with httpx.Client(timeout=15.0, headers={"Accept": "application/dns-json",
                                                  "User-Agent": DEFAULT_UA}) as client:
            for prefix in DNS_AID_NAMES:
                name = f"{prefix}.{host}"
                answer = client.get(DOH_RESOLVER, params={"name": name, "type": "SVCB",
                                                          "do": "1"}).json()
                records = [r for r in answer.get("Answer", []) if r.get("type") in {SVCB, HTTPS_RR}]
                if records:
                    found.append(name)
                    validated = validated or bool(answer.get("AD"))
    except (httpx.HTTPError, ValueError) as exc:
        state.record("dns_aid", UNMEASURED, f"DNS over HTTPS failed: {type(exc).__name__}", host)
        return

    if found and validated:
        state.record("dns_aid", PASS, "DNSSEC-validated records at " + ", ".join(found), host)
    elif found:
        state.record("dns_aid", FAIL, "records at " + ", ".join(found) + " are not DNSSEC-validated", host)
        state.missing("dns_aid", "agent.dns_aid_missing", host,
                      "SVCB records exist at " + ", ".join(found) + " but the resolver did not "
                      "return authenticated data, and the draft requires DNSSEC")
    else:
        state.record("dns_aid", FAIL, "no SVCB records under _agents", host)
        state.missing("dns_aid", "agent.dns_aid_missing", host,
                      "no SVCB record at " + ", ".join(f"{p}.{host}" for p in DNS_AID_NAMES))


def check_ard(state: Run) -> None:
    current = state.probe.document("/.well-known/ard.json")
    doc = current if current.found else state.probe.document("/.well-known/ai-catalog.json")
    if not doc.found:
        state.record("ard", FAIL, "no manifest at ard.json or ai-catalog.json", current.url)
        return
    if doc is not current:
        state.emit("agent.ard_legacy_location", doc.url,
                   "manifest served at /.well-known/ai-catalog.json and not at ard.json")
    entries = doc.data.get("entries") if isinstance(doc.data, dict) else None
    if doc.error or not isinstance(entries, list) or not entries:
        reason = doc.error or "no non-empty entries array"
        state.record("ard", FAIL, reason, doc.url)
        state.emit("agent.ard_invalid", doc.url, reason)
        return
    state.record("ard", PASS, f"{len(entries)} entries", doc.url)


# ---------------------------------------------------------------------------
# Commerce, informational and outside the ladder


def check_commerce(state: Run) -> None:
    _check_acp(state)
    _check_ucp(state)
    _check_mpp(state)
    _check_x402(state)
    _check_ap2(state)


def _check_acp(state: Run) -> None:
    doc = state.probe.document("/.well-known/acp.json")
    if not doc.found:
        state.record("acp", FAIL, doc.note, doc.url)
        state.missing("acp", "agent.commerce_acp_absent", doc.url, f"/.well-known/acp.json {doc.note}")
        return
    data = doc.data if isinstance(doc.data, dict) else {}
    protocol = data.get("protocol") if isinstance(data.get("protocol"), dict) else {}
    missing = []
    if protocol.get("name") != "acp":
        missing.append('protocol.name "acp"')
    if not protocol.get("version"):
        missing.append("protocol.version")
    if not str(data.get("api_base_url", "")).startswith(("https://", "http://")):
        missing.append("absolute api_base_url")
    if not data.get("transports"):
        missing.append("transports")
    if not (data.get("capabilities") or {}).get("services"):
        missing.append("capabilities.services")
    if doc.error or missing:
        reason = doc.error or "missing " + ", ".join(missing)
        state.record("acp", FAIL, reason, doc.url)
        state.emit("agent.commerce_acp_invalid", doc.url, reason)
        return
    state.record("acp", PASS, f"ACP {protocol['version']}", doc.url)


def _check_ucp(state: Run) -> None:
    doc = state.probe.document("/.well-known/ucp")
    if not doc.found:
        state.record("ucp", FAIL, doc.note, doc.url)
        state.missing("ucp", "agent.commerce_ucp_absent", doc.url, f"/.well-known/ucp {doc.note}")
        return
    data = doc.data if isinstance(doc.data, dict) else {}
    profile = data.get("ucp") if isinstance(data.get("ucp"), dict) else None
    if profile is not None:
        missing = [k for k in ("version", "services", "payment_handlers") if k not in profile]
        shape = f"UCP {profile.get('version', '?')}"
    else:
        # The shape the scanner's prompt describes, from earlier releases.
        missing = [k for k in ("protocol_version", "services", "capabilities", "endpoints")
                   if k not in data]
        shape = f"older top-level shape, protocol_version {data.get('protocol_version', '?')}"
    if doc.error or missing:
        reason = doc.error or "missing " + ", ".join(missing)
        state.record("ucp", FAIL, reason, doc.url)
        state.emit("agent.commerce_ucp_invalid", doc.url, reason)
        return
    state.record("ucp", PASS, shape, doc.url)


def _check_mpp(state: Run) -> None:
    doc = state.probe.document("/openapi.json")
    if not doc.found or doc.error or not isinstance(doc.data, dict):
        note = doc.note if not doc.found else (doc.error or "not a JSON object")
        state.record("mpp", FAIL, note, doc.url)
        state.missing("mpp", "agent.commerce_mpp_absent", doc.url, f"/openapi.json {note}")
        return

    offers, problems = 0, []
    for path, item in (doc.data.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method, operation in item.items():
            info = operation.get("x-payment-info") if isinstance(operation, dict) else None
            if not info:
                continue
            for offer in info.get("offers", [info]) if isinstance(info, dict) else []:
                offers += 1
                lacking = [k for k in ("intent", "method") if not offer.get(k)]
                if "amount" not in offer:
                    lacking.append("amount")
                if offer.get("intent") and offer["intent"] not in {"charge", "session"}:
                    lacking.append("intent of charge or session")
                if lacking:
                    problems.append(f"{method.upper()} {path}: missing {', '.join(lacking)}")
    if not offers:
        state.record("mpp", FAIL, "openapi.json has no x-payment-info", doc.url)
        state.missing("mpp", "agent.commerce_mpp_absent", doc.url,
                      "/openapi.json exists but no operation carries x-payment-info")
        return
    if problems:
        state.emit("agent.commerce_mpp_invalid", doc.url, "; ".join(problems[:5]))
    state.record("mpp", PASS, f"{offers} payable offer(s)", doc.url)


def _check_x402(state: Run) -> None:
    home = state.probe.src.absolute("/")
    if not state.probe.live:
        state.record("x402", UNMEASURED, "a 402 response needs a live server", home)
        return
    for path in ("/", "/api", "/api/v1"):
        resp = state.probe.get(path)
        if resp.status != 402:
            continue
        url = state.probe.src.absolute(path)
        described = "payment-required" in resp.headers or '"x402version"' in resp.text().lower()
        if not described:
            state.record("x402", FAIL, f"{path} returns 402 with no payment requirements", url)
            state.emit("agent.commerce_x402_invalid", url,
                       f"{path} returned 402 without a PAYMENT-REQUIRED header or x402 body")
            return
        state.record("x402", PASS, f"{path} returns 402 with payment requirements", url)
        return
    state.record("x402", FAIL, "no 402 at /, /api or /api/v1", home)
    state.missing("x402", "agent.commerce_x402_absent", home, "none of /, /api, /api/v1 returned 402")


def _check_ap2(state: Run) -> None:
    card = getattr(state, "a2a_card", None)
    url = state.probe.src.absolute("/.well-known/agent-card.json")
    if not card:
        state.record("ap2", FAIL, "AP2 is declared on an A2A Agent Card, and there is none", url)
        state.missing("ap2", "agent.commerce_ap2_absent", url,
                      "no A2A Agent Card, so there is nowhere to declare AP2")
        return
    extensions = (card.get("capabilities") or {}).get("extensions") or []
    uris = [str(e.get("uri", "")) for e in extensions if isinstance(e, dict)]
    if any("ap2" in uri.lower() for uri in uris):
        state.record("ap2", PASS, "AP2 extension on the Agent Card", url)
        return
    state.record("ap2", FAIL, "Agent Card declares no AP2 extension", url)
    state.missing("ap2", "agent.commerce_ap2_absent", url,
                  "capabilities.extensions on the Agent Card has no AP2 entry")


# ---------------------------------------------------------------------------
# Comparison with Cloudflare's scanner


#: Why the two answers can differ for a check, where the reason is known.
KNOWN_DIFFERENCES = {
    "ai_rules": "the scanner's bot list includes tokens Anthropic retired and omits ClaudeBot",
    "mcp_card": "the scanner reads SEP-1649 paths; SEP-2127 moves the card",
    "webmcp": "the scanner runs the page in a browser; siteseo reads it statically",
    "a2a_card": "siteseo accepts a pre-1.0 card and reports it as legacy",
    "ard": "siteseo reads both ard.json and the older ai-catalog.json",
    "link_headers": "the scanner's list of agent Link relations is not published",
    "markdown_negotiation": "both test the homepage only",
    "sitemap": "siteseo follows the robots.txt Sitemap line on the same host",
    "ucp": "siteseo accepts both the current ucp object and the older top-level shape",
}


def compare_cloudflare(cfg, result: dict, *, timeout: float = 120.0) -> dict:
    """Ask isitagentready.com for its answer and line the two up.

    Opt-in and never part of the gate: it sends the site URL to a third party
    and waits on its scan.
    """
    _require_network()
    ref = reference()
    try:
        with httpx.Client(timeout=timeout, headers={"User-Agent": DEFAULT_UA}) as client:
            resp = client.post(ref["scanner"]["scan_api"], json={"url": cfg.site})
            resp.raise_for_status()
            scan = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        return {"available": False, "reason": f"{type(exc).__name__}: {exc}"}

    ours = {row["check"]: row for row in result["checks"]}
    rows = []
    for standard in ref.get("standards", []):
        group, key = standard["scanner"].split(".", 1)
        theirs = ((scan.get("checks") or {}).get(group) or {}).get(key) or {}
        mine = ours.get(standard["check"], {})
        agree = _statuses_agree(mine.get("status"), theirs.get("status"))
        rows.append({
            "check": standard["check"],
            "label": standard["name"],
            "siteseo": mine.get("status", SKIPPED),
            "cloudflare": theirs.get("status", "absent"),
            "cloudflare_message": theirs.get("message", ""),
            "agree": agree,
            "known_reason": "" if agree else KNOWN_DIFFERENCES.get(standard["check"], ""),
        })

    return {
        "available": True,
        "scanned_at": scan.get("scannedAt"),
        "cloudflare_level": scan.get("level"),
        "cloudflare_level_name": scan.get("levelName"),
        "cloudflare_is_commerce": scan.get("isCommerce"),
        "siteseo_level": result["level"],
        "rows": rows,
        "disagreements": [row for row in rows if row["agree"] is False],
    }


def _statuses_agree(mine: str | None, theirs: str | None) -> bool | None:
    """True or False when both gave a definite answer, None when either did not."""
    if mine not in {PASS, FAIL} or theirs not in {PASS, FAIL}:
        return None
    return mine == theirs


# ---------------------------------------------------------------------------
# Output


def render(result: dict, comparison: dict | None = None) -> str:
    lines = [
        f"Agent readiness for {result['site']}",
        f"  profile {result['profile']}, source {result['source_kind']}",
        "",
        f"Level {result['level']} of 5: {result['level_name']}",
    ]
    if result.get("ceiling"):
        lines.append(f"  {result['ceiling']}")
    upcoming = result.get("next_level")
    if upcoming:
        lines.append(
            f"  Level {upcoming['level']} ({upcoming['name']}) needs {upcoming['rule']}: "
            + ", ".join(upcoming["needs"])
        )
    lines += ["", "  Reported on its own. It never moves search health or AI access.", ""]

    lines.append(f"  {'check':34s} {'status':11s} detail")
    lines.append("  " + "-" * 90)
    for check in result["checks"]:
        lines.append(f"  {check['label'][:34]:34s} {check['status']:11s} {check['summary'][:80]}")

    if result["findings"]:
        lines += ["", f"{len(result['findings'])} findings:"]
        for finding in result["findings"]:
            lines.append(f"  [{finding['severity']}] {finding['id']}: {finding['evidence'][:140]}")

    if comparison is not None:
        lines.append("")
        if not comparison.get("available"):
            lines.append(f"Cloudflare comparison unavailable: {comparison.get('reason')}")
        else:
            lines.append(
                f"Cloudflare's scanner: level {comparison['cloudflare_level']} "
                f"({comparison['cloudflare_level_name']}), siteseo: level {comparison['siteseo_level']}"
            )
            if not comparison["disagreements"]:
                lines.append("  No check where both gave a definite answer disagrees.")
            for row in comparison["disagreements"]:
                reason = f" ({row['known_reason']})" if row["known_reason"] else ""
                lines.append(
                    f"  {row['label']}: siteseo {row['siteseo']}, Cloudflare {row['cloudflare']}{reason}"
                )

    lines.append("")
    for note in result["notes"]:
        lines.append(f"Note: {note}")
    return "\n".join(lines)


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Module O: agent readiness")
    parser.add_argument("--live", action="store_true", help="check the deployed site over HTTP")
    parser.add_argument("--compare-cloudflare", action="store_true",
                        help="also run Cloudflare's public scanner and list disagreements")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = run(cfg, live=args.live)
    comparison = compare_cloudflare(cfg, result) if args.compare_cloudflare else None
    if args.json:
        if comparison is not None:
            result["cloudflare"] = comparison
        print(json.dumps(result, indent=2))
    else:
        print(render(result, comparison))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

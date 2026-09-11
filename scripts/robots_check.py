"""robots.txt parsing and evaluation, following RFC 9309.

Written rather than borrowed because the AI crawler matrix depends on getting
precedence exactly right, and because Python's urllib.robotparser does not
implement RFC 9309 longest-match rule precedence. The test suite in
tests/test_robots_rfc9309.py runs both against the same cases so the difference
stays visible.

The rules that matter, from RFC 9309 section 2.2.2:

  - Group selection is by user-agent product token, case-insensitive. The
    longest matching token wins. The "*" group applies only when no specific
    token matches at all.
  - Within the selected group, the rule with the longest path pattern wins,
    counting octets of the pattern with wildcards expanded as literal
    characters.
  - When an allow rule and a disallow rule are equally specific, allow wins.
  - An empty Disallow value grants access.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse

DIRECTIVE = re.compile(r"^\s*([A-Za-z-]+)\s*:\s*(.*?)\s*$")


@dataclass
class Rule:
    allow: bool
    pattern: str
    line_number: int

    @property
    def specificity(self) -> int:
        """Octet length of the pattern. RFC 9309 section 2.2.2."""
        return len(self.pattern)

    def matches(self, path: str) -> bool:
        return _pattern_matches(self.pattern, path)

    def __str__(self) -> str:
        return f"{'Allow' if self.allow else 'Disallow'}: {self.pattern}"


@dataclass
class Group:
    agents: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    start_line: int = 0


@dataclass
class ParseError:
    line_number: int
    line: str
    reason: str


@dataclass
class Robots:
    groups: list[Group] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)
    raw: str = ""
    fetch_status: int = 200

    # ---- group selection -------------------------------------------------

    def group_for(self, user_agent: str) -> Group | None:
        """The group that applies to this crawler, by longest token match."""
        token = _product_token(user_agent)
        best: Group | None = None
        best_length = -1
        wildcard: Group | None = None

        for group in self.groups:
            for agent in group.agents:
                if agent == "*":
                    if wildcard is None:
                        wildcard = group
                    continue
                agent_lower = agent.lower()
                if agent_lower in token and len(agent_lower) > best_length:
                    best, best_length = group, len(agent_lower)

        return best if best is not None else wildcard

    # ---- evaluation ------------------------------------------------------

    def decide(self, user_agent: str, url_or_path: str) -> tuple[bool, Rule | None]:
        """Return (allowed, deciding rule). No rule means allowed by default."""
        if self.fetch_status >= 500:
            # RFC 9309 section 2.3.1.4: a server error means disallow all.
            return False, None
        if self.fetch_status == 404 or self.fetch_status >= 400:
            # Unavailable means no restrictions.
            return True, None

        path = _request_path(url_or_path)
        group = self.group_for(user_agent)
        if group is None:
            return True, None

        winner: Rule | None = None
        for rule in group.rules:
            if not rule.matches(path):
                continue
            if winner is None:
                winner = rule
                continue
            if rule.specificity > winner.specificity:
                winner = rule
            elif rule.specificity == winner.specificity and rule.allow and not winner.allow:
                # Equally specific: allow wins.
                winner = rule

        if winner is None:
            return True, None
        return winner.allow, winner

    def allowed(self, user_agent: str, url_or_path: str) -> bool:
        return self.decide(user_agent, url_or_path)[0]

    def blocked_paths_for(self, user_agent: str) -> list[str]:
        group = self.group_for(user_agent)
        if group is None:
            return []
        return [rule.pattern for rule in group.rules if not rule.allow and rule.pattern]


def _product_token(user_agent: str) -> str:
    """Lowercased user agent, which is what a token is matched against."""
    return (user_agent or "").lower()


def _request_path(url_or_path: str) -> str:
    if url_or_path.startswith(("http://", "https://")):
        parsed = urlparse(url_or_path)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return path
    return url_or_path or "/"


def _pattern_matches(pattern: str, path: str) -> bool:
    """RFC 9309 section 2.2.3 path matching, with * and $ wildcards."""
    if pattern == "":
        return False

    # Percent-encoding is compared after normalisation on both sides.
    pattern = unquote(pattern)
    path = unquote(path)

    anchored_end = pattern.endswith("$")
    if anchored_end:
        pattern = pattern[:-1]

    if "*" not in pattern:
        return path == pattern if anchored_end else path.startswith(pattern)

    parts = pattern.split("*")
    regex = ".*".join(re.escape(part) for part in parts)
    regex = f"^{regex}$" if anchored_end else f"^{regex}"
    return re.search(regex, path) is not None


def parse(text: str, *, fetch_status: int = 200) -> Robots:
    """Parse robots.txt content. Unknown directives are ignored, per RFC 9309."""
    robots = Robots(raw=text, fetch_status=fetch_status)
    current: Group | None = None
    # A user-agent line after rules starts a new group.
    accepting_agents = False

    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        match = DIRECTIVE.match(line)
        if not match:
            robots.errors.append(
                ParseError(number, raw_line.strip(), "line is not `field: value`")
            )
            continue

        field_name = match.group(1).lower()
        value = match.group(2)

        if field_name == "user-agent":
            if not value:
                robots.errors.append(
                    ParseError(number, raw_line.strip(), "User-agent has no value")
                )
                continue
            if current is None or not accepting_agents:
                current = Group(start_line=number)
                robots.groups.append(current)
                accepting_agents = True
            current.agents.append(value)
            continue

        if field_name in {"allow", "disallow"}:
            if current is None:
                robots.errors.append(
                    ParseError(
                        number,
                        raw_line.strip(),
                        f"{match.group(1)} appears before any User-agent line",
                    )
                )
                continue
            accepting_agents = False
            if field_name == "disallow" and value == "":
                # An empty Disallow grants access. Recorded, never enforced.
                continue
            if value and not value.startswith("/") and not value.startswith("*"):
                robots.errors.append(
                    ParseError(
                        number,
                        raw_line.strip(),
                        "path should start with / or *",
                    )
                )
            current.rules.append(Rule(allow=field_name == "allow", pattern=value, line_number=number))
            continue

        if field_name == "sitemap":
            if value:
                robots.sitemaps.append(value)
            else:
                robots.errors.append(
                    ParseError(number, raw_line.strip(), "Sitemap has no value")
                )
            continue

        # crawl-delay, host and anything else: not part of RFC 9309, ignored.

    return robots


# --------------------------------------------------------------------------
# CLI


def main() -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Parse and evaluate robots.txt")
    parser.add_argument("path_or_url", help="a robots.txt file, or a site URL to fetch it from")
    parser.add_argument("--agent", action="append", default=[], help="user agent to evaluate")
    parser.add_argument("--path", action="append", default=["/"], help="path to evaluate")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from pathlib import Path

    target = args.path_or_url
    status = 200
    if target.startswith(("http://", "https://")):
        import httpx

        url = target.rstrip("/") + "/robots.txt" if not target.endswith("robots.txt") else target
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=20)
            text, status = resp.text, resp.status_code
        except httpx.HTTPError as exc:
            print(f"Could not fetch {url}: {exc}", file=sys.stderr)
            return 1
    else:
        path = Path(target)
        if not path.is_file():
            print(f"No such file: {path}", file=sys.stderr)
            return 1
        text = path.read_text(encoding="utf-8", errors="replace")

    robots = parse(text, fetch_status=status)

    result = {
        "fetch_status": status,
        "groups": [
            {"agents": g.agents, "rules": [str(r) for r in g.rules]} for g in robots.groups
        ],
        "sitemaps": robots.sitemaps,
        "errors": [
            {"line": e.line_number, "text": e.line, "reason": e.reason} for e in robots.errors
        ],
        "decisions": [],
    }

    for agent in args.agent or ["*"]:
        for path_value in args.path:
            allowed, rule = robots.decide(agent, path_value)
            result["decisions"].append(
                {
                    "agent": agent,
                    "path": path_value,
                    "allowed": allowed,
                    "rule": str(rule) if rule else "no matching rule",
                }
            )

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f"robots.txt  status {status}  {len(robots.groups)} groups")
    for group in robots.groups:
        print(f"  User-agent: {', '.join(group.agents)}")
        for rule in group.rules:
            print(f"    {rule}")
    if robots.sitemaps:
        print(f"  Sitemaps: {', '.join(robots.sitemaps)}")
    for error in robots.errors:
        print(f"  line {error.line_number}: {error.reason}  ({error.line})")
    print()
    for decision in result["decisions"]:
        verdict = "allowed" if decision["allowed"] else "BLOCKED"
        print(f"  {verdict:8s} {decision['agent']:22s} {decision['path']:30s} {decision['rule']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

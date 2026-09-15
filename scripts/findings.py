"""The finding record and the check catalog.

Every check siteseo can emit is declared once in
`skills/siteseo/reference/checks.yaml`, which carries the module, the default
severity, which score the check counts against, the rule in one line, a source
URL backing the rule, the fix text, and whether a fix can be applied
automatically.

Code never invents a finding id. It calls `make()` with an id that exists in the
catalog, and the catalog supplies everything except the URLs and the evidence.
That is what makes the acceptance criterion "every finding has evidence and a
source URL" enforceable rather than aspirational.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml

SEVERITIES = ("error", "warning", "notice")
SCORES = ("search", "ai", "both", "none")
MODULES = tuple("ABCDEFGHIJKLMNO")


def plugin_root() -> Path:
    override = os.environ.get("SITESEO_PLUGIN_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent


def catalog_path() -> Path:
    return plugin_root() / "skills" / "siteseo" / "reference" / "checks.yaml"


class UnknownCheck(KeyError):
    """Raised when code emits a finding id that is not in the catalog."""


@dataclass
class Check:
    id: str
    module: str
    severity: str
    score: str
    rule: str
    source: str
    fix: str
    autofix: bool = False

    def __post_init__(self) -> None:
        if self.module not in MODULES:
            raise ValueError(f"{self.id}: module {self.module!r} is not A through O")
        if self.severity not in SEVERITIES:
            raise ValueError(f"{self.id}: severity {self.severity!r} is not one of {SEVERITIES}")
        if self.score not in SCORES:
            raise ValueError(f"{self.id}: score {self.score!r} is not one of {SCORES}")
        if not self.source.startswith(("http://", "https://", "RFC ")):
            raise ValueError(f"{self.id}: source must be a URL or an RFC reference")
        if not self.rule.strip():
            raise ValueError(f"{self.id}: rule is empty")
        if not self.fix.strip():
            raise ValueError(f"{self.id}: fix is empty")


@lru_cache(maxsize=1)
def catalog() -> dict[str, Check]:
    path = catalog_path()
    if not path.is_file():
        raise FileNotFoundError(f"check catalog missing at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    checks: dict[str, Check] = {}
    for entry in raw.get("checks", []):
        check = Check(**entry)
        if check.id in checks:
            raise ValueError(f"duplicate check id in catalog: {check.id}")
        checks[check.id] = check
    if not checks:
        raise ValueError(f"check catalog at {path} declares no checks")
    return checks


@dataclass
class Finding:
    id: str
    module: str
    severity: str
    score: str
    urls: list[str]
    evidence: str
    source: str
    fix: str
    autofix: bool = False
    #: Discriminator for merging. Findings sharing an id and severity collapse
    #: into one only when their group also matches. Module E sets this to the
    #: crawler token, because "remove the Disallow for GPTBot" and "remove the
    #: Disallow for ClaudeBot" are two different fixes, not forty URLs behind
    #: one fix.
    group: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["detail"]:
            data.pop("detail")
        if not data["group"]:
            data.pop("group")
        return data


def make(
    check_id: str,
    urls: str | Iterable[str],
    evidence: str,
    *,
    severity: str | None = None,
    group: str = "",
    detail: dict[str, Any] | None = None,
) -> Finding:
    """Build a finding from a catalog id.

    `severity` may be raised or lowered for a specific instance (a warning that
    is an error on a sitemap URL, say), but never invented from nothing.
    """
    try:
        check = catalog()[check_id]
    except KeyError as exc:
        raise UnknownCheck(
            f"{check_id!r} is not in the check catalog. Add it to "
            f"reference/checks.yaml before emitting it."
        ) from exc

    if isinstance(urls, str):
        url_list = [urls]
    else:
        url_list = list(urls)

    evidence = (evidence or "").strip()
    if not evidence:
        raise ValueError(f"{check_id}: a finding must carry raw evidence")

    if severity is not None and severity not in SEVERITIES:
        raise ValueError(f"{check_id}: severity {severity!r} is not one of {SEVERITIES}")

    return Finding(
        id=check.id,
        module=check.module,
        severity=severity or check.severity,
        score=check.score,
        urls=url_list,
        evidence=evidence,
        source=check.source,
        fix=check.fix,
        autofix=check.autofix,
        group=group,
        detail=detail or {},
    )


def merge(findings: Iterable[Finding]) -> list[Finding]:
    """Collapse findings that share an id and a severity into one with all URLs.

    One template change that clears forty URLs should appear once. Evidence from
    the first instance is kept, and the count goes in detail so the report can
    say how many URLs are behind it.
    """
    grouped: dict[tuple[str, str, str], Finding] = {}
    for finding in findings:
        key = (finding.id, finding.severity, finding.group)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = Finding(**{**asdict(finding), "urls": list(finding.urls)})
            continue
        seen = set(existing.urls)
        existing.urls.extend(url for url in finding.urls if url not in seen)
    for finding in grouped.values():
        finding.detail["url_count"] = len(finding.urls)
    return list(grouped.values())


SEVERITY_ORDER = {"error": 0, "warning": 1, "notice": 2}


def sort_key(finding: Finding) -> tuple[int, str, str]:
    return (SEVERITY_ORDER.get(finding.severity, 9), finding.module, finding.id)


def order(findings: Iterable[Finding]) -> list[Finding]:
    """Errors, then warnings, then notices, module order inside each band."""
    return sorted(findings, key=sort_key)


def dumps(findings: Iterable[Finding], **kwargs: Any) -> str:
    return json.dumps([f.to_dict() for f in findings], indent=2, **kwargs)


def loads(text: str) -> list[Finding]:
    return [Finding(**row) for row in json.loads(text)]


def counts(findings: Iterable[Finding]) -> dict[str, int]:
    totals = {"error": 0, "warning": 0, "notice": 0}
    for finding in findings:
        totals[finding.severity] = totals.get(finding.severity, 0) + 1
    return totals

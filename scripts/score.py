"""Two scores, never blended.

Search health and AI access measure different things and move independently. A
site can be technically excellent and invisible to AI assistants because a CDN
rule blocks them, or wide open to every crawler while its canonicals are a mess.
Averaging those into one number destroys the only information the reader needs.

Both formulas are deliberately simple and printed alongside the numbers, so a
score can be argued with. A score nobody can reconstruct is a score nobody
should trust.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Each distinct warning TYPE costs this much, once, however many URLs it hits.
#: Per-type rather than per-URL: one template bug is one problem.
WARNING_TYPE_PENALTY = 1.5
#: Cap so warnings alone cannot drive the score to zero.
MAX_WARNING_DEDUCTION = 30.0
#: Main content that only exists after JavaScript runs costs this much of AI
#: access, because most AI crawlers read the first HTML response and stop.
JS_DEPENDENCY_PENALTY = 25.0

SEARCH_MODULES = {"A", "B", "C", "D"}


@dataclass
class Score:
    name: str
    value: float
    basis: str
    components: dict[str, float] = field(default_factory=dict)
    unavailable: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": round(self.value, 1),
            "basis": self.basis,
            "components": {k: round(v, 2) for k, v in self.components.items()},
            "unavailable": self.unavailable,
        }


def search_health(findings: list[dict], urls_checked: int) -> Score:
    """Share of checked URLs carrying no module A-D error, less a warning penalty."""
    if urls_checked <= 0:
        return Score("search health", 0.0, "no URLs were checked", {})

    failing: set[str] = set()
    warning_types: set[str] = set()

    for finding in findings:
        if finding.get("module") not in SEARCH_MODULES:
            continue
        if finding.get("score") not in {"search", "both"}:
            continue
        if finding["severity"] == "error":
            failing.update(finding.get("urls", []))
        elif finding["severity"] == "warning":
            warning_types.add(finding["id"])

    clean_share = (urls_checked - len(failing)) / urls_checked * 100.0
    deduction = min(len(warning_types) * WARNING_TYPE_PENALTY, MAX_WARNING_DEDUCTION)
    value = max(0.0, clean_share - deduction)

    return Score(
        name="search health",
        value=value,
        basis=(
            f"{urls_checked - len(failing)} of {urls_checked} URLs carry no error in "
            f"modules A to D ({clean_share:.1f}%), less {deduction:.1f} for "
            f"{len(warning_types)} distinct warning types"
        ),
        components={
            "urls_checked": float(urls_checked),
            "urls_with_errors": float(len(failing)),
            "clean_share": clean_share,
            "warning_types": float(len(warning_types)),
            "warning_deduction": deduction,
        },
    )


def ai_access(bots: list[dict], js_dependent_pages: int = 0, pages_checked: int = 0) -> Score:
    """Share of policy-allowed crawlers passing every module E test.

    Crawlers the policy blocks are excluded from the denominator: deliberately
    blocking a training crawler is a choice, not a failure. A crawler is counted
    as passing only when robots.txt allows it AND no sampled fetch was refused.
    """
    allowed = [bot for bot in bots if bot.get("intended") == "allow"]
    unavailable: list[str] = []

    if not allowed:
        return Score(
            "AI access",
            100.0,
            "policy blocks every crawler, so there is nothing to measure",
            {"allowed_bots": 0.0},
        )

    passing = 0
    for bot in allowed:
        # `effective_allowed` is the module E verdict and the single source of
        # truth. Recomputing it here once produced a different answer: scoring
        # counted any non-200 as a block, including a URL that returns 403 to
        # everyone, which made one broken page look like every crawler being
        # refused.
        if not bot.get("effective_allowed"):
            continue
        if not bot.get("fetch_tested"):
            unavailable.append(bot["token"])
        passing += 1

    share = passing / len(allowed) * 100.0

    penalty = 0.0
    if pages_checked and js_dependent_pages:
        penalty = JS_DEPENDENCY_PENALTY * (js_dependent_pages / pages_checked)

    value = max(0.0, share - penalty)

    basis = (
        f"{passing} of {len(allowed)} policy-allowed crawlers pass every test "
        f"({share:.1f}%)"
    )
    if penalty:
        basis += (
            f", less {penalty:.1f} because {js_dependent_pages} of {pages_checked} "
            "pages need JavaScript for their main content"
        )

    return Score(
        name="AI access",
        value=value,
        basis=basis,
        components={
            "allowed_bots": float(len(allowed)),
            "passing_bots": float(passing),
            "share": share,
            "js_dependent_pages": float(js_dependent_pages),
            "js_penalty": penalty,
        },
        unavailable=(
            [
                f"{len(unavailable)} of {len(allowed)} crawlers were judged on robots.txt "
                "alone because no fetch test reached the site"
            ]
            if unavailable
            else []
        ),
    )


def both(findings: list[dict], urls_checked: int, bots: list[dict],
         js_dependent_pages: int = 0, pages_checked: int = 0) -> dict:
    """Both scores, side by side. They are never combined into one number."""
    search = search_health(findings, urls_checked)
    access = ai_access(bots, js_dependent_pages, pages_checked)
    return {"search_health": search.to_dict(), "ai_access": access.to_dict()}


def render(scores: dict, previous: dict | None = None) -> str:
    lines = []
    for key, label in (("search_health", "Search health"), ("ai_access", "AI access")):
        current = scores.get(key) or {}
        value = current.get("value")
        if value is None:
            continue
        line = f"  {label:14s} {value:5.1f}"
        if previous and previous.get(key, {}).get("value") is not None:
            was = previous[key]["value"]
            delta = value - was
            arrow = "same as" if abs(delta) < 0.05 else ("up from" if delta > 0 else "down from")
            line += f"   ({arrow} {was:.1f})"
        lines.append(line)
        lines.append(f"                 {current.get('basis', '')}")
        for note in current.get("unavailable", []):
            lines.append(f"                 not measured: {note}")
    lines.append("")
    lines.append("  These two are never combined. A site can be technically sound and")
    lines.append("  still refuse every AI crawler, or the reverse.")
    return "\n".join(lines)

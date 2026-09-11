"""Turn an audit into a brief for whichever agent maintains the site.

siteseo observes. It does not know the site's templating language, its brand
voice, or why a page exists. The agent working in that repository does. So the
audit ends with a section addressed to that agent: what is wrong, which pages it
costs the most, and what to decide. How to change the code stays its call.

Priority comes from evidence rather than severity alone. A missing meta
description on a page earning 900 impressions is worth more than an error on a
page nobody has ever reached. Without Search Console or Analytics connected,
ordering falls back to severity and says so, because a confident ranking built
on no data is worse than an honest unranked list.
"""

from __future__ import annotations

from urllib.parse import urlparse

#: Findings whose fix is a judgement call the site's own agent should make.
NEEDS_JUDGEMENT = {
    "content.not_original",
    "content.answer_not_near_top",
    "content.cannibalization",
    "index.noindex_but_linked",
    "duplicate.identical_content",
    "duplicate.near_duplicate",
    "title.too_long",
    "title.too_short",
    "meta_description.too_long",
    "links.no_inbound",
    "structure.orphan_url",
}

SEVERITY_WEIGHT = {"error": 100.0, "warning": 20.0, "notice": 3.0}


def _path(url: str) -> str:
    return urlparse(url).path or "/"


def page_value(gsc: dict | None, analytics: dict | None) -> dict[str, dict]:
    """How much traffic each path actually carries, by path."""
    value: dict[str, dict] = {}

    for row in (gsc or {}).get("rows_page", []) or []:
        keys = row.get("keys") or []
        if not keys:
            continue
        entry = value.setdefault(_path(keys[0]), {})
        entry["impressions"] = entry.get("impressions", 0) + row.get("impressions", 0)
        entry["clicks"] = entry.get("clicks", 0) + row.get("clicks", 0)

    for row in (analytics or {}).get("pages", []) or []:
        path = row.get("pagePath") or ""
        if not path:
            continue
        entry = value.setdefault(path.split("?")[0], {})
        entry["views"] = entry.get("views", 0) + (row.get("screenPageViews") or 0)

    return value


def rank(findings: list[dict], value: dict[str, dict]) -> list[dict]:
    """Order findings by the traffic they affect, not by severity alone."""
    ranked = []
    for finding in findings:
        weight = SEVERITY_WEIGHT.get(finding["severity"], 1.0)
        impressions = clicks = views = 0.0
        for url in finding.get("urls", []):
            entry = value.get(_path(url), {})
            impressions += entry.get("impressions", 0)
            clicks += entry.get("clicks", 0)
            views += entry.get("views", 0)

        # Traffic multiplies the severity weight rather than replacing it, so an
        # error on a quiet page still outranks a notice on a busy one.
        reach = impressions + (clicks * 10) + views
        ranked.append({
            **finding,
            "_score": weight * (1 + reach / 100.0),
            "_impressions": impressions,
            "_clicks": clicks,
            "_views": views,
        })
    return sorted(ranked, key=lambda f: -f["_score"])


def render(snapshot: dict, gsc: dict | None = None,
           analytics: dict | None = None) -> str:
    """The section addressed to the agent that maintains this site."""
    findings = snapshot.get("findings", [])
    value = page_value(gsc, analytics)
    has_data = bool(value)
    ordered = rank(findings, value)

    out: list[str] = []
    out.append("## For the agent maintaining this site")
    out.append("")
    out.append(
        "siteseo checked this site and cannot change it. You know the templates, "
        "the voice and why each page exists, so what follows is evidence and a "
        "recommendation, not an instruction. Decide what to act on."
    )
    out.append("")

    if has_data:
        out.append(
            "Ordering below is by the traffic each finding actually affects, "
            "combining Search Console impressions and clicks with Analytics "
            "pageviews. A warning on a page people reach outranks an error on a "
            "page nobody has found."
        )
    else:
        out.append(
            "Neither Search Console nor Analytics is connected, so ordering is by "
            "severity alone. That is a weaker signal: it cannot tell a page that "
            "matters from one nobody visits. Connect them and this section ranks "
            "by real reach instead."
        )
    out.append("")

    actionable = [f for f in ordered if f["severity"] in ("error", "warning")]
    if not actionable:
        out.append("Nothing at error or warning severity. Notices are listed in the report above.")
        return "\n".join(out) + "\n"

    out.append("### Do these first")
    out.append("")
    for finding in actionable[:10]:
        urls = finding.get("urls", [])
        where = urls[0] if len(urls) == 1 else f"{len(urls)} pages"
        out.append(f"**{finding['id']}** on {where}")
        out.append("")
        out.append(f"- What is wrong: {finding['evidence']}")
        out.append(f"- Suggested fix: {finding['fix']}")
        if has_data:
            out.append(
                f"- Reach: {int(finding['_impressions'])} impressions, "
                f"{int(finding['_clicks'])} clicks, {int(finding['_views'])} pageviews"
            )
        if finding["id"] in NEEDS_JUDGEMENT:
            out.append(
                "- This one is your call. The right answer depends on what the page "
                "is for, which siteseo cannot see."
            )
        if finding.get("autofix"):
            out.append(
                f"- Mechanical: `/siteseo fix {finding['id']}` will draft a diff, "
                "but read it before applying."
            )
        out.append(f"- Why it matters: {finding.get('source', '')}")
        out.append("")

    out.append("### Rules to follow when you act")
    out.append("")
    out.append(
        "- Edit source, not build output. A change to the built directory is "
        "overwritten by the next build and looks fixed when it is not."
    )
    out.append(
        "- Fix the generator when a finding repeats across many pages. The same "
        "defect on thirty pages is one template, not thirty edits."
    )
    out.append(
        "- Leave anything that needs judgement to a human if you are unsure. "
        "Rewriting a title changes what the page claims to be."
    )
    out.append(
        "- Re-run `/siteseo audit` afterwards. The snapshot diff will show what "
        "your change actually moved."
    )
    out.append("")

    if has_data:
        out.extend(_what_is_working(gsc, analytics))

    return "\n".join(out) + "\n"


def _what_is_working(gsc: dict | None, analytics: dict | None) -> list[str]:
    """The other half of the question: what is already earning attention."""
    out = ["### What is already working", ""]

    rows = (gsc or {}).get("rows_page", []) or []
    if rows:
        best = sorted(rows, key=lambda r: -(r.get("clicks") or 0))[:5]
        out.append("Pages earning the most clicks in search:")
        out.append("")
        for row in best:
            keys = row.get("keys") or [""]
            out.append(
                f"- {_path(keys[0])}: {int(row.get('clicks', 0))} clicks from "
                f"{int(row.get('impressions', 0))} impressions, "
                f"position {row.get('position', 0):.1f}"
            )
        out.append("")
        out.append(
            "Protect these. Check any change against them before and after, and "
            "look at what they do that the quiet pages do not."
        )
        out.append("")

    referrals = (analytics or {}).get("ai_referrals") or {}
    if referrals:
        out.append("AI assistants are sending traffic:")
        out.append("")
        for label, count in referrals.items():
            out.append(f"- {label}: {int(count)} sessions")
        out.append("")
        out.append(
            "This is the only first-party evidence that AI visibility work is "
            "doing anything. Watch it across runs rather than reading one number."
        )
        out.append("")
    elif analytics is not None:
        out.append(
            "No AI assistant referrals yet. That is common and is not by itself a "
            "problem: assistants often answer without a click. Read it alongside "
            "the crawler matrix, which says whether they can reach the site at all."
        )
        out.append("")

    return out

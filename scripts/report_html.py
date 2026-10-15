"""Render an audit snapshot as a branded, plain-English HTML report.

The Markdown report is written for whoever maintains the site's code. This one
is written for the person who owns the site: every problem is named in plain
words from the catalog's `title`, repeated findings are grouped into one item
with a page count, and the site's own logo sits at the top so the report can be
handed to a client or a manager as it is.

The page is a single self-contained file: styles inline, logo embedded, no
scripts loaded from anywhere. It prints cleanly, and `--pdf` saves the same page
as a PDF through the Chromium that `siteseo setup --chromium` installs.
"""

from __future__ import annotations

import html
from collections import OrderedDict
from datetime import datetime
from urllib.parse import urlparse

import brief as brief_module
import history
from findings import catalog

SEVERITY = {
    "error": ("Fix now", "stop"),
    "warning": ("Worth fixing", "flag"),
    "notice": ("Small things", "note"),
}

PURPOSE = {
    "training": "Learns from your content",
    "search": "Builds an AI search index",
    "user_fetch": "Reads a page when someone asks",
}

AREAS = OrderedDict([
    ("A", "Can search engines find and read your pages"),
    ("B", "Titles, descriptions, headings and images"),
    ("C", "Details for richer search listings"),
    ("D", "Page speed"),
    ("E", "Access for AI assistants"),
    ("F", "Content quality"),
    ("G", "Links between your pages"),
    ("H", "Other languages and countries"),
    ("I", "Local business details"),
    ("J", "Google Search Console and Bing data"),
    ("K", "How often AI assistants mention you"),
    ("L", "Keyword research"),
    ("M", "Links from other websites"),
    ("N", "Google Analytics data"),
    ("O", "Readiness for AI agents"),
])

#: Why an area did not run, in the words of the person reading the report.
NOT_RUN = {
    "D": "Needs a free Google PageSpeed key. The setup guide shows how to get one.",
    "H": "Your site has no other-language versions, so this did not apply.",
    "I": "No local business details were found, so this did not apply.",
    "J": "Connect Google Search Console to include your search data.",
    "N": "Connect Google Analytics to include your visitor data.",
}
SEPARATE_STEP = {
    "F": "Reviewed page by page when you ask Claude, not in this automatic check.",
    "K": "Runs on its own when you ask, after showing what it will cost.",
    "L": "Paid research that runs only when you ask for it.",
    "M": "Uses link reports you export and add yourself.",
}

SITESEO_MARK = (
    '<svg viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="14" fill="#1E3A8A"/>'
    '<circle cx="28" cy="28" r="14" fill="none" stroke="#fff" stroke-width="6"/>'
    '<line x1="38.5" y1="38.5" x2="50" y2="50" stroke="#fff" stroke-width="7" stroke-linecap="round"/>'
    '<path d="M21.5 28.5l4.5 4.5 8.5-9.5" fill="none" stroke="#34D399" stroke-width="4.5" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)

STYLE = """
:root { --night:#0B1B3F; --navy:#1E3A8A; --signal:#34D399; --leaf:#047857; --mist:#EEF2FA;
  --stop:#B91C1C; --stop-bg:#FEECEC; --flag:#B45309; --flag-bg:#FEF3C7; --note:#475569; --note-bg:#F1F5F9;
  --ink:#0B1B3F; --body:#334155; --muted:#64748B; --line:#DCE3F0; }
* { box-sizing: border-box; }
body { margin: 0; background: #E9EEF7; color: var(--body); font: 15px/1.6 "Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif; }
.sheet { max-width: 900px; margin: 28px auto; background: #fff; border-radius: 16px; box-shadow: 0 20px 50px -30px rgba(11,27,63,.45); overflow: hidden; }
header.cover { padding: 36px 44px 30px; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; gap: 24px; align-items: center; }
header.cover .logo { height: 56px; width: auto; max-width: 280px; object-fit: contain; object-position: left center; display: block; }
header.cover .site { font-size: 22px; font-weight: 700; color: var(--ink); }
header.cover .meta { text-align: right; color: var(--muted); font-size: 14px; }
header.cover .meta strong { display: block; color: var(--ink); font-size: 20px; }
main { padding: 8px 44px 40px; }
h2 { color: var(--ink); font-size: 22px; margin: 36px 0 6px; letter-spacing: -.01em; }
h2 + p.lead { margin-top: 0; color: var(--muted); }
.scores { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 26px; }
.score { border-radius: 14px; padding: 18px 20px; background: var(--mist); }
.score .label { font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
.score .value { font-size: 40px; font-weight: 800; color: var(--ink); line-height: 1.1; margin-top: 6px; }
.score .value small { font-size: 16px; color: var(--muted); font-weight: 600; }
.score .change { font-size: 13px; font-weight: 600; }
.score .change.up { color: var(--leaf); } .score .change.down { color: var(--stop); }
.score p { margin: 8px 0 0; font-size: 13px; }
.score.ai { background: #E3F7EE; }
.tally { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }
.chip { display: inline-block; white-space: nowrap; font-size: 13px; font-weight: 700; padding: 5px 12px; border-radius: 999px; }
.chip.stop { color: var(--stop); background: var(--stop-bg); }
.chip.flag { color: var(--flag); background: var(--flag-bg); }
.chip.note { color: var(--note); background: var(--note-bg); }
.chip.ok { color: var(--leaf); background: #E3F7EE; }
.fix { border: 1px solid var(--line); border-radius: 14px; padding: 18px 20px; margin-top: 12px; page-break-inside: avoid; break-inside: avoid; }
.fix .top { display: flex; gap: 14px; align-items: flex-start; }
.fix .rank { flex: none; width: 32px; height: 32px; border-radius: 9px; background: var(--night); color: #fff; font-weight: 800; display: grid; place-items: center; }
.fix h3 { margin: 2px 0 4px; font-size: 17px; color: var(--ink); }
.fix .tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }
.fix dl { display: grid; grid-template-columns: 120px 1fr; gap: 6px 14px; margin: 14px 0 0; font-size: 14px; }
.fix dt { color: var(--muted); font-weight: 600; }
.fix dd { margin: 0; }
.fix details { margin-top: 10px; font-size: 13px; }
.fix summary { cursor: pointer; color: var(--navy); font-weight: 600; }
.fix ul { margin: 6px 0 0; padding-left: 18px; word-break: break-all; }
table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }
th { text-align: left; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); padding: 8px 10px; border-bottom: 2px solid var(--line); }
td { padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
td small { display: block; color: var(--muted); }
tr { page-break-inside: avoid; break-inside: avoid; }
.small-list { columns: 2; column-gap: 28px; padding-left: 18px; margin: 10px 0 0; }
.small-list li { break-inside: avoid; margin-bottom: 6px; }
.small-list span { color: var(--muted); }
.note-box { background: var(--mist); border-radius: 12px; padding: 14px 18px; margin-top: 14px; font-size: 14px; }
.note-box ul { margin: 6px 0 0; padding-left: 18px; }
footer { border-top: 1px solid var(--line); padding: 18px 44px 26px; display: flex; gap: 10px; align-items: center; color: var(--muted); font-size: 13px; }
footer svg { width: 22px; height: 22px; flex: none; }
footer a { color: var(--navy); }
@media (max-width: 700px) {
  header.cover, main, footer { padding-left: 20px; padding-right: 20px; }
  header.cover { flex-direction: column; align-items: flex-start; }
  header.cover .meta { text-align: left; }
  .scores { grid-template-columns: 1fr; }
  .small-list { columns: 1; }
  .fix dl { grid-template-columns: 1fr; }
}
@page { size: A4; margin: 14mm; }
@media print {
  body { background: #fff; }
  .sheet { margin: 0; box-shadow: none; border-radius: 0; max-width: none; }
  h2 { break-after: avoid; }
}
"""

PRINT_SCRIPT = (
    "<script>window.addEventListener('beforeprint',function(){"
    "document.querySelectorAll('details').forEach(function(d){d.open=true;});});</script>"
)


def _e(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def _title(finding: dict) -> str:
    if finding.get("title"):
        return finding["title"]
    check = catalog().get(finding.get("id", ""))
    return check.title if check else finding.get("id", "")


def _why(finding: dict) -> str:
    check = catalog().get(finding.get("id", ""))
    return check.why if check else ""


def _group(findings: list[dict]) -> list[dict]:
    """One item per check, however many crawlers or variants raised it."""
    grouped: "OrderedDict[str, dict]" = OrderedDict()
    for finding in findings:
        key = finding["id"]
        item = grouped.get(key)
        if item is None:
            grouped[key] = {**finding, "urls": list(finding.get("urls", [])), "_count": 1}
            continue
        seen = set(item["urls"])
        item["urls"].extend(u for u in finding.get("urls", []) if u not in seen)
        item["_count"] += 1
        for field in ("_score", "_impressions", "_clicks", "_views"):
            if field in finding:
                item[field] = item.get(field, 0) + finding[field]
        rank = {"error": 0, "warning": 1, "notice": 2}
        if rank.get(finding["severity"], 9) < rank.get(item["severity"], 9):
            item["severity"] = finding["severity"]
    return list(grouped.values())


def _path(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")


def _score_card(key: str, label: str, scores: dict, prior: dict | None, explain: str, css: str) -> str:
    current = scores.get(key) or {}
    value = current.get("value")
    shown = "n/a" if value is None else f"{value:.0f}"
    change = ""
    if value is not None and prior and (prior.get(key) or {}).get("value") is not None:
        delta = value - prior[key]["value"]
        if abs(delta) >= 0.5:
            change = (f'<div class="change {"up" if delta > 0 else "down"}">'
                      f'{"Up" if delta > 0 else "Down"} {abs(delta):.0f} since last report</div>')
        else:
            change = '<div class="change">Same as last report</div>'
    return (f'<div class="score {css}"><div class="label">{_e(label)}</div>'
            f'<div class="value">{shown}<small> / 100</small></div>{change}<p>{_e(explain)}</p></div>')


def _fix_item(n: int, item: dict, has_data: bool) -> str:
    sev_label, sev_css = SEVERITY.get(item["severity"], ("", "note"))
    urls = item.get("urls", [])
    tags = [f'<span class="chip {sev_css}">{sev_label}</span>']
    if urls:
        tags.append(f'<span class="chip note">{len(urls)} page{"s" if len(urls) != 1 else ""}</span>')
    if item.get("autofix"):
        tags.append('<span class="chip ok">siteseo can fix this</span>')
    if item["id"] in brief_module.NEEDS_JUDGEMENT:
        tags.append('<span class="chip note">Your call</span>')

    rows = [("Why it matters", _why(item)), ("How to fix it", item.get("fix", ""))]
    if has_data:
        reach = (f'{int(item.get("_views", 0))} page views, {int(item.get("_impressions", 0))} '
                 f'search impressions, {int(item.get("_clicks", 0))} clicks')
        rows.append(("Visitors affected", reach))
    rows.append(("What we saw", item.get("evidence", "")))
    dl = "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in rows if v)
    source = item.get("source", "")
    if source.startswith("http"):
        dl += f'<dt>Source</dt><dd><a href="{_e(source)}">{_e(urlparse(source).netloc)}</a></dd>'

    pages = ""
    if urls:
        listed = "".join(f"<li>{_e(_path(u))}</li>" for u in urls[:25])
        more = f"<li>and {len(urls) - 25} more</li>" if len(urls) > 25 else ""
        pages = f"<details><summary>Show the pages</summary><ul>{listed}{more}</ul></details>"

    return (f'<div class="fix"><div class="top"><div class="rank">{n}</div><div>'
            f'<h3>{_e(_title(item))}</h3><div class="tags">{"".join(tags)}</div></div></div>'
            f'<dl>{dl}</dl>{pages}</div>')


def _crawler_table(bots: list[dict]) -> str:
    rows = []
    for bot in bots:
        allowed = bot.get("intended") == "allow"
        if not bot.get("fetch_tested"):
            got = '<span class="chip note">Not tested</span>'
        elif bot.get("effective_allowed"):
            got = '<span class="chip ok">Yes</span>'
        else:
            got = '<span class="chip stop">Turned away</span>'
        robots = "Allowed" if bot.get("robots_allowed") else "Blocked"
        ok = '<span class="chip ok">As intended</span>' if bot.get("matches_policy") else '<span class="chip stop">Not as intended</span>'
        rows.append(
            f"<tr><td><strong>{_e(bot.get('token'))}</strong><small>{_e(bot.get('operator'))}</small></td>"
            f"<td>{_e(PURPOSE.get(bot.get('purpose'), bot.get('purpose', '')))}</td>"
            f"<td>{'Allow' if allowed else 'Block'}</td><td>{robots}</td><td>{got}</td><td>{ok}</td></tr>"
        )
    return ("<table><thead><tr><th>Visitor</th><th>What it does</th><th>You want</th>"
            "<th>robots.txt says</th><th>Got in</th><th>Result</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def _areas(snapshot: dict) -> str:
    import report as md_report

    findings = snapshot.get("findings", [])
    ran = set(snapshot.get("modules") or [])
    skipped = {}
    for entry in snapshot.get("skipped") or []:
        head, _, reason = entry.partition(":")
        parts = head.strip().split(" ")
        if len(parts) > 1 and parts[0] == "module":
            skipped[parts[1]] = reason.strip()
    rows = []
    for letter, area in AREAS.items():
        mine = [f for f in findings if f.get("module") == letter]
        if letter in skipped:
            status, why = '<span class="chip note">Not checked</span>', NOT_RUN.get(letter, skipped[letter])
        elif letter in md_report.NOT_IN_AUDIT and letter not in ran:
            status, why = '<span class="chip note">Separate step</span>', SEPARATE_STEP.get(letter, md_report.NOT_IN_AUDIT[letter])
        elif letter not in ran:
            status, why = '<span class="chip note">Not checked</span>', ""
        elif not mine:
            status, why = '<span class="chip ok">No problems</span>', ""
        else:
            ids = {f["id"] for f in mine}
            worst = min(mine, key=lambda f: {"error": 0, "warning": 1, "notice": 2}.get(f["severity"], 9))
            label, css = SEVERITY[worst["severity"]]
            status, why = f'<span class="chip {css}">{len(ids)} to look at</span>', ""
        rows.append(f"<tr><td>{_e(area)}</td><td>{status}</td><td><small>{_e(why)}</small></td></tr>")
    return ("<table><thead><tr><th>Area</th><th>Result</th><th></th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def _since_last(findings: list[dict], prior: dict | None) -> str:
    if prior is None:
        return ""
    delta = history.diff_findings(findings, prior.get("findings", []))
    if not delta["new"] and not delta["resolved"]:
        return '<h2>Since the last report</h2><p class="lead">Nothing changed.</p>'
    out = ["<h2>Since the last report</h2>"]
    for key, label, css in (("resolved", "Fixed", "ok"), ("new", "New", "flag")):
        items = _group(delta[key])
        if not items:
            continue
        out.append(f'<p><span class="chip {css}">{label}: {len(items)}</span></p><ul class="small-list">')
        for item in items:
            count = len(item.get("urls", []))
            out.append(f"<li>{_e(_title(item))} <span>({count} page{'s' if count != 1 else ''})</span></li>")
        out.append("</ul>")
    return "".join(out)


def render(snapshot: dict, prior: dict | None = None, logo=None, version: str = "") -> str:
    site = snapshot.get("site", "")
    host = urlparse(site).netloc or site
    when = snapshot.get("recorded_at", "")
    try:
        date = datetime.fromisoformat(when).strftime("%B %d, %Y").replace(" 0", " ")
    except ValueError:
        date = when[:10]
    findings = snapshot.get("findings", [])
    scores = snapshot.get("scores", {})
    prior_scores = (prior or {}).get("scores")

    value = brief_module.page_value(snapshot.get("search_performance"), snapshot.get("analytics"))
    has_data = bool(value)
    ranked = _group(brief_module.rank(findings, value))
    ranked.sort(key=lambda f: -f.get("_score", 0))
    actionable = [f for f in ranked if f["severity"] in ("error", "warning")]
    notices = [f for f in ranked if f["severity"] == "notice"]
    tally = {s: sum(1 for f in ranked if f["severity"] == s) for s in ("error", "warning", "notice")}

    brand = (f'<img class="logo" src="{logo.data_uri()}" alt="{_e(host)}">' if logo is not None
             else f'<div class="site">{_e(host)}</div>')

    agent = snapshot.get("agent_readiness") or {}
    agent_card = ""
    if agent:
        agent_card = (
            f'<div class="score"><div class="label">AI agent readiness</div>'
            f'<div class="value">{agent.get("level", 0)}<small> / 5</small></div>'
            f'<p>{_e(agent.get("level_name", ""))}. How easily AI agents can find and use what your site offers.</p></div>'
        )

    stats = snapshot.get("stats") or {}
    pages = stats.get("pages_200") or stats.get("pages_crawled") or 0

    parts = [
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">",
        f"<title>Website report for {_e(host)}, {_e(date)}</title><style>{STYLE}</style></head><body>",
        '<div class="sheet"><header class="cover">',
        f"<div>{brand}</div>",
        f'<div class="meta"><strong>Website report</strong>{_e(host)}<br>{_e(date)}</div></header><main>',
        '<div class="scores">',
        _score_card("search_health", "Search health", scores, prior_scores,
                    "How well search engines can find, read and list your pages.", ""),
        _score_card("ai_access", "AI access", scores, prior_scores,
                    "How many of the AI assistants you allow can actually read your site.", "ai"),
        agent_card,
        "</div>",
        '<div class="tally">',
        f'<span class="chip stop">{tally["error"]} to fix now</span>',
        f'<span class="chip flag">{tally["warning"]} worth fixing</span>',
        f'<span class="chip note">{tally["notice"]} small things</span>',
        f'<span class="chip note">{pages} pages checked</span>',
        "</div>",
    ]

    parts.append("<h2>Fix these first</h2>")
    parts.append(
        '<p class="lead">'
        + ("Ranked by how many visitors each problem touches, from your Google Search Console "
           "and Analytics data." if has_data else
           "Ranked by how serious each problem is. Connect Google Search Console and Analytics "
           "to rank them by the visitors they affect instead.")
        + "</p>"
    )
    if actionable:
        parts.extend(_fix_item(n, item, has_data) for n, item in enumerate(actionable[:12], start=1))
        if len(actionable) > 12:
            parts.append(f'<p class="lead">{len(actionable) - 12} more are listed in the Markdown report.</p>')
    else:
        parts.append('<p><span class="chip ok">Nothing serious found</span></p>')

    if snapshot.get("bots"):
        parts.append("<h2>Can AI assistants read your site?</h2>")
        parts.append('<p class="lead">Each AI service sends its own visitor. This is what you want each one '
                     "to do, what your robots.txt file tells it, and what happened when siteseo visited as it.</p>")
        parts.append(_crawler_table(snapshot["bots"]))

    if notices:
        parts.append("<h2>Small things</h2>")
        parts.append('<p class="lead">Not urgent. Worth a look when you next work on these pages.</p><ul class="small-list">')
        for item in notices:
            count = len(item.get("urls", []))
            parts.append(f"<li>{_e(_title(item))} <span>({count} page{'s' if count != 1 else ''})</span></li>")
        parts.append("</ul>")

    parts.append(_since_last(findings, prior))

    parts.append("<h2>Everything we checked</h2>")
    parts.append(_areas(snapshot))

    notes = [n for n in (snapshot.get("notes") or []) if "no response from" not in n]
    if notes:
        parts.append('<div class="note-box"><strong>Good to know</strong><ul>')
        parts.extend(f"<li>{_e(n)}</li>" for n in notes[:8])
        parts.append("</ul></div>")

    credit = f"siteseo {version}" if version else "siteseo"
    found = f" Logo from {_e(logo.found_by)}." if logo is not None else ""
    parts.append(
        "</main><footer>" + SITESEO_MARK
        + f'<span>Prepared with <a href="https://siteseo.davidsoden.com/">{_e(credit)}</a>. '
        f"Every finding links to the published rule behind it.{found}</span></footer></div>"
        + PRINT_SCRIPT + "</body></html>"
    )
    return "".join(parts)


def write_pdf(html_path, pdf_path) -> str | None:
    """Save the HTML report as a PDF. Returns an error message, or None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "Playwright is not installed. Run siteseo setup."
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri())
            page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
            page.emulate_media(media="print")
            page.pdf(path=str(pdf_path), format="A4", print_background=True,
                     margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"})
            browser.close()
    except Exception as exc:  # noqa: BLE001
        return (f"Could not make the PDF ({exc.__class__.__name__}). It needs Chromium: run "
                '"${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" setup --chromium. The HTML report was saved.')
    return None

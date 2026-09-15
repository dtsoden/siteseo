"""The host rule that serves exported Markdown for `Accept: text/markdown`.

`/siteseo markdown` writes the files. Static files cannot look at a request
header, so something at the host has to choose the `.md` when an agent asks for
it. This generates that piece for the host named in siteseo.yaml, or the one
passed with `--serve`, and follows the same rule as fix mode: it prints what it
would write and writes nothing without `--apply`. An existing file is never
overwritten.

Every handler comes from `skills/siteseo/templates/markdown/`. The nginx one is
tested against nginx in Docker; the JavaScript handlers are exercised by the
test suite under Node with each platform's request objects faked.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import findings as F

HOSTS = ("cloudflare-pages", "cloudflare-worker", "netlify", "vercel", "nginx")


@dataclass
class Plan:
    host: str
    files: list[tuple[str, str]] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    unsupported: str = ""


def templates() -> Path:
    return F.plugin_root() / "skills" / "siteseo" / "templates" / "markdown"


def render_template(name: str, cfg) -> str:
    text = (templates() / name).read_text(encoding="utf-8")
    helpers = (templates() / "helpers.js").read_text(encoding="utf-8").rstrip()
    host = urlparse(cfg.site).hostname or "example.com"
    zone = host[4:] if host.startswith("www.") else host
    return (
        text.replace("// {{HELPERS}}", helpers)
        .replace("{{SITE_HOST}}", host)
        .replace("{{ZONE}}", zone)
        .replace("{{COMPATIBILITY_DATE}}", date.today().isoformat())
    )


def plan(cfg, host: str | None = None) -> Plan:
    chosen = host or cfg.host
    if chosen == "cloudflare-pages":
        return Plan(chosen, [("functions/_middleware.js", "cloudflare-pages-middleware.js")], [
            "Commit functions/_middleware.js at the project root, beside your build output, "
            "not inside it.",
            "Deploy. Every request now runs the function, which counts against the Workers "
            "free quota of 100,000 requests a day.",
        ])
    if chosen == "cloudflare-worker":
        return Plan(chosen, [
            ("siteseo-markdown-worker/src/index.js", "cloudflare-worker.js"),
            ("siteseo-markdown-worker/wrangler.jsonc", "wrangler.jsonc"),
        ], [
            "The site's DNS record must be proxied (orange cloud) in Cloudflare.",
            "Check zone_name in wrangler.jsonc matches the domain in your dashboard.",
            "Deploy from siteseo-markdown-worker/ with: npx wrangler deploy",
        ])
    if chosen == "netlify":
        return Plan(chosen, [("netlify/edge-functions/siteseo-markdown.js", "netlify-edge-function.js")], [
            "Commit netlify/edge-functions/ at the project root and deploy.",
            "Add a Vary: Accept header for /* in _headers or netlify.toml, so caches keep the "
            "HTML and Markdown versions apart.",
        ])
    if chosen == "vercel":
        return Plan(chosen, [("middleware.mjs", "vercel-middleware.mjs")], [
            "Add @vercel/functions to package.json dependencies.",
            "Deploy to a preview first and run /siteseo agents --live against the preview URL.",
            "Vercel picks the Content-Type for .md files. If the check reports anything other "
            "than text/markdown, add a headers rule for /(.*).md in vercel.json.",
        ])
    if chosen == "nginx":
        return Plan(chosen, [("siteseo-markdown.nginx.conf", "nginx.conf")], [
            "Merge the snippet into the server's own config: the map blocks into http, the rest "
            "into the server block for this site. Keep your own root and listen lines.",
            "Run nginx -t, then reload nginx.",
        ])
    if chosen == "github-pages":
        return Plan(chosen, unsupported=(
            "GitHub Pages cannot vary a response on a request header or set custom headers, so "
            "it cannot serve Markdown for Accept: text/markdown on its own. The Markdown files "
            "and <link rel=\"alternate\"> tags still work for agents that follow links. For "
            "negotiation, put the domain behind Cloudflare and run --serve cloudflare-worker."
        ))
    return Plan(chosen or "other", unsupported=(
        f"No serving rule is known for host {chosen!r}. Pass --serve with one of: "
        + ", ".join(HOSTS)
        + ". A site whose DNS is proxied through Cloudflare can use cloudflare-worker "
        "whatever it is hosted on."
    ))


@dataclass
class Change:
    path: Path
    content: str
    state: str  # create, identical, conflict

    def diff(self) -> str:
        before = self.path.read_text(encoding="utf-8").splitlines(keepends=True) if self.path.exists() else []
        return "".join(difflib.unified_diff(
            before, self.content.splitlines(keepends=True),
            fromfile=f"a/{self.path.name}", tofile=f"b/{self.path.name}",
        ))


def changes(cfg, current: Plan) -> list[Change]:
    out = []
    for relative, template in current.files:
        path = cfg.root / relative
        content = render_template(template, cfg)
        if not path.exists():
            state = "create"
        elif path.read_text(encoding="utf-8") == content:
            state = "identical"
        else:
            state = "conflict"
        out.append(Change(path, content, state))
    return out


def main(cfg, *, host: str | None = None, apply: bool = False, as_json: bool = False) -> int:
    current = plan(cfg, host)
    if current.unsupported:
        if as_json:
            print(json.dumps({"host": current.host, "supported": False, "reason": current.unsupported}))
        else:
            print(current.unsupported)
        return 2

    proposed = changes(cfg, current)
    written: list[str] = []
    if apply:
        for change in proposed:
            if change.state == "create":
                change.path.parent.mkdir(parents=True, exist_ok=True)
                change.path.write_bytes(change.content.encode("utf-8"))
                written.append(str(change.path))

    if as_json:
        print(json.dumps({
            "host": current.host,
            "supported": True,
            "files": [{"path": str(c.path), "state": c.state, "diff": c.diff()} for c in proposed],
            "steps": current.steps,
            "written": written,
        }, indent=2))
        return 0

    lines = [f"Serving Markdown for Accept: text/markdown on {current.host}", ""]
    for change in proposed:
        if change.state == "identical":
            lines.append(f"  already in place: {change.path}")
            continue
        if change.state == "conflict":
            lines.append(f"  {change.path} exists with different content. Not overwriting; merge by hand:")
        else:
            lines.append(f"  create {change.path}")
        lines.extend("    " + line for line in change.diff().splitlines())
        lines.append("")
    lines.append("Then:")
    lines.extend(f"  - {step}" for step in current.steps)
    lines.append("  - Run /siteseo agents --live to confirm agents get Markdown.")
    lines.append("")
    if apply:
        lines.append(f"Wrote {len(written)} file(s)." if written else "Nothing new to write.")
    else:
        lines.append("Nothing has been written. Re-run with --apply to create the new files above.")
    print("\n".join(lines))
    return 0

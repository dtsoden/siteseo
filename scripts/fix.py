"""Fix mode: propose diffs, apply nothing without a yes.

Two rules hold everywhere in this file.

First, siteseo edits SOURCE, never build output. Editing `dist/` produces a file
that the next build silently overwrites, which looks like a fix and is not one.
When the source for a finding cannot be located, the fix is reported as manual
rather than guessed at.

Second, nothing is written without a diff and an explicit confirmation. `--apply`
is the confirmation; without it this prints what it would do and stops.

Content rewrites, page deletions and any change to a noindex directive stay
manual by design. Those are judgement calls and a tool should not make them.
"""

from __future__ import annotations

import difflib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


# Where each stack keeps files that end up at the site root.
PUBLIC_DIRS = {
    "astro": ["public"],
    "next": ["public"],
    "hugo": ["static"],
    "eleventy": ["public", "static", "src"],
    "plain-html": ["."],
    "other": ["public", "static", "."],
    "auto": ["public", "static", "src", "."],
}

STACK_MARKERS = {
    "astro": ["astro.config.mjs", "astro.config.ts", "astro.config.js"],
    "next": ["next.config.js", "next.config.mjs", "next.config.ts"],
    "hugo": ["hugo.toml", "config.toml", "hugo.yaml"],
    "eleventy": [".eleventy.js", "eleventy.config.js"],
}

# Redirect file format per host.
REDIRECT_TARGET = {
    "netlify": "_redirects",
    "cloudflare-pages": "_redirects",
    "github-pages": None,
    "vercel": "vercel.json",
    "other": None,
}

MANUAL_ONLY = {
    "content.not_original",
    "content.answer_not_near_top",
    "index.noindex_but_linked",
    "index.noindex_in_sitemap",
    "canonical.target_noindex",
    "duplicate.near_duplicate",
    "duplicate.identical_content",
}


@dataclass
class Proposal:
    finding_id: str
    path: Path
    before: str
    after: str
    reason: str
    manual: bool = False
    note: str = ""

    @property
    def diff(self) -> str:
        return "".join(
            difflib.unified_diff(
                self.before.splitlines(keepends=True),
                self.after.splitlines(keepends=True),
                fromfile=f"a/{self.path.name}",
                tofile=f"b/{self.path.name}",
                n=3,
            )
        )


@dataclass
class Plan:
    proposals: list[Proposal] = field(default_factory=list)
    manual: list[tuple[str, str]] = field(default_factory=list)
    unmatched: list[tuple[str, str]] = field(default_factory=list)
    content: list[tuple[str, str]] = field(default_factory=list)


def detect_stack(cfg) -> str:
    if cfg.stack != "auto":
        return cfg.stack
    for stack, markers in STACK_MARKERS.items():
        for marker in markers:
            if (cfg.root / marker).is_file():
                return stack
    return "plain-html"


def public_dir(cfg, stack: str) -> Path:
    for candidate in PUBLIC_DIRS.get(stack, ["public"]):
        path = cfg.root / candidate
        if path.is_dir():
            return path
    target = cfg.root / PUBLIC_DIRS.get(stack, ["public"])[0]
    return target


# ---------------------------------------------------------------- fixers


def fix_robots(cfg, stack: str, finding: dict) -> Proposal | None:
    """Rewrite robots.txt so it matches ai_policy. Source file, not build output."""
    target = public_dir(cfg, stack) / "robots.txt"
    before = target.read_text(encoding="utf-8") if target.is_file() else ""
    after = generate_robots(cfg, before)
    if after == before:
        return None
    return Proposal(
        finding["id"],
        target,
        before,
        after,
        reason="regenerate robots.txt from ai_policy in siteseo.yaml",
    )


def generate_robots(cfg, existing: str = "") -> str:
    """Build robots.txt from the declared policy, keeping any Sitemap lines."""
    import ai_matrix

    blocked_training = cfg.ai_policy.training == "block"
    blocked_search = cfg.ai_policy.search_and_user_fetch == "block"

    lines = ["User-agent: *", "Allow: /", ""]

    for bot in ai_matrix.load_bots():
        should_block = (
            blocked_training if bot.purpose == "training" else blocked_search
        )
        if should_block:
            lines.append(f"# {bot.operator}: {bot.purpose}")
            lines.append(f"User-agent: {bot.token}")
            lines.append("Disallow: /")
            lines.append("")

    sitemaps = [
        line.strip()
        for line in existing.splitlines()
        if line.strip().lower().startswith("sitemap:")
    ]
    if not sitemaps:
        sitemaps = [f"Sitemap: {cfg.origin}/sitemap.xml"]
    lines.extend(sitemaps)
    return "\n".join(lines).rstrip() + "\n"


def fix_indexnow(cfg, stack: str, finding: dict) -> Proposal | None:
    import uuid

    # The standard library's `secrets` module is shadowed here by our vault
    # reader of the same name, so the key comes from uuid4 instead.
    key = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    target = public_dir(cfg, stack) / f"{key}.txt"
    return Proposal(
        finding["id"],
        target,
        "",
        key + "\n",
        reason=(
            "create an IndexNow key file at the site root. After deploying, ping "
            "https://api.indexnow.org/indexnow with this key on each publish."
        ),
    )


FIXERS = {
    "ai.blocked_against_policy": fix_robots,
    "ai.allowed_against_policy": fix_robots,
    "robots.invalid_syntax": fix_robots,
    "robots.no_sitemap_line": fix_robots,
    "robots.blocks_css_or_js": fix_robots,
    "ai.indexnow_key_missing": fix_indexnow,
}

#: Mechanical SEO. Structure, attributes and configuration, where the correct
#: value is determined by a rule rather than by judgement. These are the only
#: things `fix` will ever write.
MECHANICAL = {
    "robots.invalid_syntax",
    "robots.no_sitemap_line",
    "robots.blocks_css_or_js",
    "ai.blocked_against_policy",
    "ai.allowed_against_policy",
    "ai.indexnow_key_missing",
    "sitemap.missing",
    "sitemap.contains_non_200",
    "sitemap.contains_noncanonical",
    "sitemap.lastmod_is_build_time",
    "sitemap.too_many_urls",
    "index.noindex_in_sitemap",
    "canonical.missing",
    "canonical.not_absolute",
    "image.dimensions_missing",
    "image.no_lazy_loading",
    "hreflang.invalid_code",
    "hreflang.no_x_default",
    "hreflang.not_reciprocal",
    "https.no_redirect_from_http",
    "https.mixed_content",
    "host.multiple_canonical_forms",
    "redirect.chain",
    "redirect.temporary_should_be_permanent",
    "link.internal_to_redirect",
    "html.lang_missing",
    "html.viewport_missing",
    "html.charset_missing",
    "schema.missing_required_property",
    "schema.missing_recommended_property",
    "local.localbusiness_incomplete",
}

#: Content. Anything whose fix is words: what a page claims to be, how it
#: describes itself, what an image shows. `fix` never writes these, whatever
#: their autofix flag says, because the right answer depends on what the page is
#: for and on the voice of the site. They go to the agent that maintains the
#: site, through the brief at the end of the report.
CONTENT = {
    "title.missing",
    "title.too_short",
    "title.too_long",
    "meta_description.missing",
    "meta_description.too_short",
    "meta_description.too_long",
    "duplicate.title",
    "duplicate.meta_description",
    "image.alt_missing",
    "heading.h1_missing",
    "heading.h1_multiple",
    "heading.level_skipped",
    "anchor.generic",
    "anchor.empty",
    "content.thin",
    "content.not_original",
    "content.answer_not_near_top",
    "content.author_missing",
    "content.contact_missing",
    "content.updated_date_mismatch",
    "content.ctr_outlier",
    "content.decay",
    "content.cannibalization",
    "schema.none_found",
    "schema.contradicts_visible_content",
    "social.og_missing",
    "social.twitter_card_missing",
}


def build_plan(cfg, findings_list: list[dict], only: list[str] | None = None) -> Plan:
    stack = detect_stack(cfg)
    plan = Plan()
    handled: set[str] = set()

    for finding in findings_list:
        finding_id = finding["id"]
        if only and finding_id not in only:
            continue
        if not finding.get("autofix"):
            continue

        if finding_id in CONTENT:
            plan.content.append((
                finding_id,
                f"{finding['fix']} This is content, so it goes to the agent that "
                "maintains the site rather than to fix mode.",
            ))
            continue

        if finding_id in MANUAL_ONLY:
            plan.manual.append((finding_id, "this change is a judgement call and stays manual"))
            continue

        if finding_id not in MECHANICAL:
            plan.manual.append((
                finding_id,
                "not classified as mechanical, so fix mode leaves it alone",
            ))
            continue

        fixer = FIXERS.get(finding_id)
        if fixer is not None:
            if finding_id in handled or (fixer is fix_robots and "robots" in handled):
                continue
            proposal = fixer(cfg, stack, finding)
            if fixer is fix_robots:
                handled.add("robots")
            handled.add(finding_id)
            if proposal is not None:
                plan.proposals.append(proposal)
            continue

        # Mechanical, but siteseo cannot locate the source with confidence.
        # Saying what to change beats guessing at a templating language and
        # producing a build that no longer compiles.
        plan.unmatched.append(
            (
                finding_id,
                f"{finding['fix']} Edit the {stack} source that renders "
                f"{finding['urls'][0] if finding['urls'] else 'this page'}. "
                "siteseo does not rewrite template syntax it cannot verify.",
            )
        )

    return plan


def apply(plan: Plan) -> list[Path]:
    written: list[Path] = []
    for proposal in plan.proposals:
        proposal.path.parent.mkdir(parents=True, exist_ok=True)
        proposal.path.write_text(proposal.after, encoding="utf-8")
        written.append(proposal.path)
    return written


def render(plan: Plan, cfg, stack: str) -> str:
    lines = [
        f"siteseo fix  (stack detected: {stack}, source root: {cfg.root})",
        "",
        "  Mechanical SEO only: structure, attributes and configuration, where the",
        "  correct value follows from a rule. Anything made of words goes to the",
        "  agent that maintains the site.",
        "",
    ]

    if plan.proposals:
        lines.append(f"{len(plan.proposals)} file change(s) proposed:")
        lines.append("")
        for proposal in plan.proposals:
            lines.append(f"--- {proposal.path}")
            lines.append(f"    why: {proposal.reason}")
            lines.append("")
            diff = proposal.diff or f"+ create this file ({len(proposal.after)} bytes)\n"
            lines.extend("    " + line.rstrip("\n") for line in diff.splitlines())
            lines.append("")
    else:
        lines.append("No file changes proposed.")
        lines.append("")

    if plan.content:
        lines.append("Content, for the agent that maintains this site:")
        lines.append("")
        lines.append("  fix mode never writes these. The right words depend on what the")
        lines.append("  page is for and on the voice of the site, which siteseo cannot see.")
        lines.append("  They appear in the brief at the end of the audit report.")
        lines.append("")
        for finding_id, note in plan.content:
            lines.append(f"  {finding_id}")
            lines.append(f"    {note}")
        lines.append("")

    if plan.unmatched:
        lines.append("Mechanical, but the source could not be located:")
        lines.append("")
        for finding_id, note in plan.unmatched:
            lines.append(f"  {finding_id}")
            lines.append(f"    {note}")
        lines.append("")

    if plan.manual:
        lines.append("Manual by design:")
        for finding_id, note in plan.manual:
            lines.append(f"  {finding_id}: {note}")
        lines.append("")

    lines.append("Nothing has been written. Re-run with --apply to write the diffs above.")
    return "\n".join(lines)


def main() -> int:
    import argparse

    import config as config_module
    import history

    parser = argparse.ArgumentParser(description="Propose and apply safe fixes")
    parser.add_argument("ids", nargs="*", help="finding ids to fix (default: every autofixable one)")
    parser.add_argument("--apply", action="store_true", help="write the diffs")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    snapshot = history.latest(cfg, "audit")
    if snapshot is None:
        print("No audit snapshot found. Run an audit first.", file=sys.stderr)
        return 1

    stack = detect_stack(cfg)
    plan = build_plan(cfg, snapshot.get("findings", []), args.ids or None)

    if args.json:
        print(json.dumps(
            {
                "stack": stack,
                "proposals": [
                    {"id": p.finding_id, "path": str(p.path), "reason": p.reason, "diff": p.diff}
                    for p in plan.proposals
                ],
                "template_edits": plan.unmatched,
                "manual": plan.manual,
                "applied": False,
            },
            indent=2,
        ))
        return 0

    print(render(plan, cfg, stack))

    if args.apply:
        written = apply(plan)
        print()
        if written:
            print(f"Wrote {len(written)} file(s):")
            for path in written:
                print(f"  {path}")
            print("\nRebuild, then run `siteseo run gate.py` to confirm.")
        else:
            print("Nothing to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


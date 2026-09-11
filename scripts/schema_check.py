"""Module C: structured data.

Extracts JSON-LD, Microdata and RDFa and validates the types that produce rich
results against reference/rich-results.yaml.

The visible-content check is deliberately narrow. Google's structured data
policies are about markup that fabricates facts the reader cannot see, so only
price, ratingValue and reviewCount are compared against the page. An earlier
version also compared `description`, which reported a correct site as a policy
violation because its markup summarised the page in different words. A summary
is supposed to paraphrase.

Types outside the rich-result set are not guessed at. Structural types that only
appear nested, such as ListItem inside a BreadcrumbList, are passed over
entirely, and anything else is named once for the whole site rather than once
per page.

FAQPage and HowTo are never recommended here. Google narrowed FAQ rich results
to a small set of sites and dropped HowTo rich results in 2023.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any

import extruct
import yaml
from w3lib.html import get_base_url

import findings as F
from crawl import extract
from source import BuildSource, Source, open_source

WHITESPACE = re.compile(r"\s+")


def load_types() -> tuple[dict[str, dict], list[str]]:
    path = F.plugin_root() / "skills" / "siteseo" / "reference" / "rich-results.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return raw.get("types", {}), raw.get("must_match_visible", [])


def load_structural() -> set[str]:
    """Types that only appear nested inside another type."""
    path = F.plugin_root() / "skills" / "siteseo" / "reference" / "rich-results.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return set(raw.get("structural_types", []))


@dataclass
class Item:
    type_name: str
    properties: dict[str, Any]
    syntax: str
    raw: str = ""


@dataclass
class PageSchema:
    url: str
    items: list[Item] = field(default_factory=list)
    invalid_blocks: list[tuple[str, str]] = field(default_factory=list)


def _type_names(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.rsplit("/", 1)[-1].lstrip("#")]
    if isinstance(value, list):
        names: list[str] = []
        for entry in value:
            names.extend(_type_names(entry))
        return names
    return []


def _walk(node: Any, syntax: str, out: list[Item]) -> None:
    """Collect every typed object, including nested ones."""
    if isinstance(node, list):
        for entry in node:
            _walk(entry, syntax, out)
        return
    if not isinstance(node, dict):
        return

    raw_type = node.get("@type") or node.get("type")
    for name in _type_names(raw_type):
        out.append(Item(type_name=name, properties=node, syntax=syntax))

    for key, value in node.items():
        if key in {"@type", "type", "@context"}:
            continue
        _walk(value, syntax, out)


def extract_schema(url: str, html: str) -> PageSchema:
    result = PageSchema(url=url)
    base_url = get_base_url(html, url)

    # Raw JSON-LD first, so a block that does not parse is reported as such
    # rather than silently dropped by the extractor.
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.S | re.I,
    ):
        block = match.group(1)
        try:
            json.loads(block)
        except json.JSONDecodeError as exc:
            result.invalid_blocks.append((block.strip()[:160], str(exc)))

    try:
        data = extruct.extract(
            html, base_url=base_url, syntaxes=["json-ld", "microdata", "rdfa"], uniform=True
        )
    except Exception as exc:  # extruct raises a variety of parser errors
        result.invalid_blocks.append(("", f"extraction failed: {exc}"))
        return result

    for syntax, key in (("json-ld", "json-ld"), ("microdata", "microdata"), ("rdfa", "rdfa")):
        _walk(data.get(key, []), syntax, result.items)

    return result


def _visible_text(page_text: str) -> str:
    return WHITESPACE.sub(" ", page_text).lower()


def _property_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, dict):
        out: list[str] = []
        for key, inner in value.items():
            if key.startswith("@"):
                continue
            out.extend(_property_strings(inner))
        return out
    if isinstance(value, list):
        out = []
        for entry in value:
            out.extend(_property_strings(entry))
        return out
    return []


def check_page(url: str, html: str, page_text: str, src: Source,
               emitted: list[F.Finding],
               unvalidated: set[str] | None = None) -> PageSchema:
    types, must_match = load_types()
    structural = load_structural()
    if unvalidated is None:
        unvalidated = set()
    schema = extract_schema(url, html)
    visible = _visible_text(page_text)

    for block, reason in schema.invalid_blocks:
        emitted.append(
            F.make("schema.invalid_json", url, f"{reason}. Block starts: {block!r}")
        )

    seen_types: set[str] = set()
    for item in schema.items:
        name = item.type_name
        if name in seen_types and name in types:
            continue
        seen_types.add(name)

        spec = types.get(name)
        if spec is None:
            # A nested structural type is correct markup, not an unknown one.
            # Reporting ListItem inside a BreadcrumbList buries real findings.
            if name not in structural:
                unvalidated.add(name)
            continue

        if spec.get("rich_result") is False:
            emitted.append(
                F.make(
                    "schema.faq_or_howto_for_rich_results",
                    url,
                    f"{name} markup is present. {spec.get('note', '').strip()}",
                    group=name,
                )
            )
            continue

        present = {key for key in item.properties if not key.startswith("@")}
        for required in spec.get("required", []):
            if required not in present:
                emitted.append(
                    F.make(
                        "schema.missing_required_property",
                        url,
                        f"{name} is missing required property {required!r} "
                        f"(see {spec['docs']})",
                        group=f"{name}.{required}",
                    )
                )
        for recommended in spec.get("recommended", []):
            if recommended not in present:
                emitted.append(
                    F.make(
                        "schema.missing_recommended_property",
                        url,
                        f"{name} has no {recommended!r} property",
                        group=f"{name}.{recommended}",
                    )
                )

        # Facts must appear on the page the reader sees.
        for key in must_match:
            if key not in item.properties:
                continue
            for value in _property_strings(item.properties[key]):
                candidate = value.strip()
                if not candidate or candidate.startswith(("http://", "https://")):
                    continue
                if len(candidate) < 4:
                    continue
                if candidate.lower() not in visible:
                    emitted.append(
                        F.make(
                            "schema.contradicts_visible_content",
                            url,
                            f"{name}.{key} is {candidate[:80]!r} but that text does not "
                            "appear on the rendered page",
                            group=f"{name}.{key}",
                        )
                    )
                break

        # sameAs profiles must resolve.
        for value in _property_strings(item.properties.get("sameAs", [])):
            if not value.startswith(("http://", "https://")):
                continue
            if isinstance(src, BuildSource):
                continue  # external URL, no network in build mode
            response = src.fetch(value)
            if not response.ok:
                emitted.append(
                    F.make(
                        "schema.sameas_unresolvable",
                        url,
                        f"sameAs {value} returned {response.status}",
                        group=value,
                    )
                )

    return schema


def run(cfg, *, live: bool = False, max_pages: int = 500) -> dict:
    from crawl import discover

    src = open_source(cfg, live=live)
    emitted: list[F.Finding] = []
    summary: dict[str, int] = {}
    unvalidated: set[str] = set()
    pages_checked = 0

    try:
        for url in discover(src, cfg, max_pages):
            response = src.fetch(url)
            if not response.ok or not response.is_html:
                continue
            html = response.text()
            page = extract(url, response)
            schema = check_page(url, html, page.text, src, emitted, unvalidated)
            pages_checked += 1
            for item in schema.items:
                summary[item.type_name] = summary.get(item.type_name, 0) + 1
    finally:
        src.close()

    # One notice for the whole site, not one per page per type.
    if unvalidated:
        emitted.append(
            F.make(
                "schema.unknown_type",
                cfg.site,
                "siteseo validates the types that produce a rich result in Google Search. "
                "This site also uses " + ", ".join(sorted(unvalidated))
                + ", which are left alone rather than guessed at.",
            )
        )

    merged = F.order(F.merge(emitted))
    return {
        "module": "C",
        "site": cfg.site,
        "pages_checked": pages_checked,
        "types_found": dict(sorted(summary.items(), key=lambda kv: -kv[1])),
        "findings": [f.to_dict() for f in merged],
        "notes": [
            "FAQPage and HowTo are never recommended. Google narrowed FAQ rich results "
            "to a small set of sites and dropped HowTo rich results in 2023."
        ],
    }


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Module C: structured data")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-pages", type=int, default=500)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = run(cfg, live=args.live, max_pages=args.max_pages)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f"Structured data across {result['pages_checked']} pages")
    if result["types_found"]:
        for name, count in result["types_found"].items():
            print(f"  {count:4d}  {name}")
    else:
        print("  no structured data found")
    print()
    for finding in result["findings"]:
        where = finding["urls"][0] if len(finding["urls"]) == 1 else f"{len(finding['urls'])} URLs"
        print(f"  [{finding['severity']:7s}] {finding['id']:38s} {where}")
        print(f"            {finding['evidence'][:150]}")
    for note in result["notes"]:
        print(f"\nNote: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

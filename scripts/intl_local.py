"""Modules H and I: international and local.

Both stay off unless the site shows the signal. Module H activates when any page
carries hreflang. Module I activates when LocalBusiness markup or a postal
address is found. Running them everywhere would bury real findings under advice
about features the site does not use.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict

import findings as F
from crawl import discover, extract
from source import BuildSource, open_source

# ISO 639-1 language, optional ISO 3166-1 alpha-2 region, or the x-default token.
HREFLANG = re.compile(r"^(x-default|[a-z]{2}(-[A-Z]{2})?)$")
PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
POSTAL_HINT = re.compile(
    r"\b(street|st\.|avenue|ave\.|road|rd\.|suite|floor|boulevard|blvd\.?|"
    r"\d{5}(-\d{4})?|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b",
    re.I,
)
LOCAL_TYPES = {"LocalBusiness", "Restaurant", "Store", "ProfessionalService",
               "MedicalBusiness", "HomeAndConstructionBusiness", "AutomotiveBusiness"}
LOCAL_RECOMMENDED = ["telephone", "openingHoursSpecification", "geo", "url", "priceRange", "image"]


def check_hreflang(pages: dict, src, emitted: list[F.Finding]) -> dict:
    """Module H. Reciprocity, code validity, x-default, and target health."""
    declared: dict[str, dict[str, str]] = {}
    for url, page in pages.items():
        if page.hreflang:
            declared[url] = {code: href for code, href in page.hreflang}

    if not declared:
        return {"active": False, "reason": "no hreflang found, module H stays off"}

    for url, entries in declared.items():
        if "x-default" not in entries:
            emitted.append(
                F.make(
                    "hreflang.no_x_default",
                    url,
                    f"hreflang set of {len(entries)} entries has no x-default",
                    group=url,
                )
            )

        for code, href in entries.items():
            if not HREFLANG.match(code):
                emitted.append(
                    F.make(
                        "hreflang.invalid_code",
                        url,
                        f"hreflang {code!r} is not a valid language or language-region code",
                        group=code,
                    )
                )

            if not src.is_internal(href):
                continue

            response = src.fetch(href)
            if response.status and not response.ok:
                emitted.append(
                    F.make(
                        "hreflang.target_not_200",
                        url,
                        f"hreflang {code} points at {href}, which returned {response.status}",
                        group=href,
                    )
                )
                continue

            target = pages.get(href)
            if target is None and response.ok:
                target = extract(href, response)
                pages[href] = target

            if target is None:
                continue

            if target.canonical and target.canonical.rstrip("/") != href.rstrip("/"):
                emitted.append(
                    F.make(
                        "hreflang.target_not_canonical",
                        url,
                        f"hreflang {code} points at {href} whose canonical is "
                        f"{target.canonical}",
                        group=href,
                    )
                )

            back = declared.get(href, {})
            if not back:
                back = {code_: href_ for code_, href_ in target.hreflang}
            if url.rstrip("/") not in {value.rstrip("/") for value in back.values()}:
                emitted.append(
                    F.make(
                        "hreflang.not_reciprocal",
                        url,
                        f"{url} references {href} as {code}, but {href} does not "
                        "reference it back",
                        group=f"{url}|{href}",
                    )
                )

    return {
        "active": True,
        "pages_with_hreflang": len(declared),
        "languages": sorted({code for entries in declared.values() for code in entries}),
    }


def check_local(pages: dict, emitted: list[F.Finding]) -> dict:
    """Module I. Name, address and phone agreement, plus markup completeness."""
    import schema_check

    types_spec, _ = schema_check.load_types()
    local_items: list[tuple[str, dict]] = []
    phones: dict[str, set[str]] = defaultdict(set)
    address_pages: list[str] = []

    for url, page in pages.items():
        if page.status != 200:
            continue
        for raw in page.jsonld_blocks:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            found: list[dict] = []
            schema_check._walk(data, "json-ld", found)  # noqa: SLF001
            for item in found:
                if item.type_name in LOCAL_TYPES:
                    local_items.append((url, item.properties))

        if POSTAL_HINT.search(page.text or ""):
            address_pages.append(url)
        for match in PHONE.findall(page.text or ""):
            normalised = re.sub(r"\D", "", match if isinstance(match, str) else match[0])
            if 9 <= len(normalised) <= 15:
                phones[url].add(normalised)

    if not local_items and not address_pages:
        return {"active": False, "reason": "no LocalBusiness markup and no address, module I stays off"}

    # Phone agreement across pages.
    all_phones = {phone for values in phones.values() for phone in values}
    if len(all_phones) > 1:
        emitted.append(
            F.make(
                "local.nap_mismatch",
                sorted(phones),
                f"{len(all_phones)} different phone numbers appear across the site: "
                + ", ".join(sorted(all_phones)[:4]),
            )
        )

    names: set[str] = set()
    for url, properties in local_items:
        present = {key for key in properties if not key.startswith("@")}
        if isinstance(properties.get("name"), str):
            names.add(properties["name"].strip())
        missing = [key for key in LOCAL_RECOMMENDED if key not in present]
        if missing:
            emitted.append(
                F.make(
                    "local.localbusiness_incomplete",
                    url,
                    f"LocalBusiness markup has no {', '.join(missing)}",
                    group=",".join(missing),
                )
            )

    if len(names) > 1:
        emitted.append(
            F.make(
                "local.nap_mismatch",
                [url for url, _ in local_items],
                f"LocalBusiness name differs across pages: {', '.join(sorted(names))}",
                group="name",
            )
        )

    emitted.append(
        F.make(
            "local.manual_checklist",
            "https://www.google.com/business/",
            "Google Business Profile and Bing Places have no API here. Check the listing "
            "name, address, phone, hours and categories match the site by hand.",
        )
    )

    return {
        "active": True,
        "localbusiness_blocks": len(local_items),
        "pages_with_address": len(address_pages),
        "distinct_phones": sorted(all_phones),
    }


def run(cfg, *, live: bool = False, max_pages: int = 500) -> dict:
    src = open_source(cfg, live=live)
    emitted: list[F.Finding] = []
    try:
        pages = {}
        for url in discover(src, cfg, max_pages):
            response = src.fetch(url)
            if response.ok and response.is_html:
                pages[url] = extract(url, response)

        hreflang_result = check_hreflang(pages, src, emitted)
        local_result = check_local(pages, emitted)
    finally:
        src.close()

    return {
        "modules": ["H", "I"],
        "site": cfg.site,
        "hreflang": hreflang_result,
        "local": local_result,
        "findings": [f.to_dict() for f in F.order(F.merge(emitted))],
    }


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Modules H and I: international and local")
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

    for key, label in (("hreflang", "Module H (international)"), ("local", "Module I (local)")):
        block = result[key]
        if not block.get("active"):
            print(f"{label}: {block.get('reason')}")
        else:
            print(f"{label}: active")
            for field_name, value in block.items():
                if field_name != "active":
                    print(f"  {field_name}: {value}")
    print()
    for finding in result["findings"]:
        print(f"  [{finding['severity']:7s}] {finding['id']:34s} {finding['evidence'][:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


_ = BuildSource

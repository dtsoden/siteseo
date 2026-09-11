"""Modules H and I: international and local.

Both stay off unless the site declares the signal. Module H activates when a
page carries hreflang. Module I activates when a page carries LocalBusiness
family structured data, and nothing else.

Module I reads structured data and `tel:` links. It does not scan prose. An
earlier version matched addresses and phone numbers with regular expressions
over page text, which on a consultancy site reported CVE identifiers like
CVE-2025-59536 as four conflicting phone numbers, and the words "factory floor"
and "Rimini Street" as postal addresses. None of it was true. Structured data is
where a site declares itself a local business, so that is the only place this
module looks.
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

LOCAL_TYPES = {"LocalBusiness", "Restaurant", "Store", "ProfessionalService",
               "MedicalBusiness", "HomeAndConstructionBusiness", "AutomotiveBusiness",
               "LegalService", "FinancialService", "FoodEstablishment", "LodgingBusiness"}

#: Wanted by a business people visit. A service-area business that declares
#: areaServed instead of address is not missing anything, so these are only
#: checked when the markup shows a physical location.
STOREFRONT_RECOMMENDED = ["telephone", "address", "openingHoursSpecification", "geo", "image"]
#: Wanted by any local business, storefront or service-area.
COMMON_RECOMMENDED = ["telephone", "url", "image"]


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


def _local_blocks(pages: dict) -> list[tuple[str, dict]]:
    """Every LocalBusiness-family structured data block, with the page it is on."""
    import schema_check

    found: list[tuple[str, dict]] = []
    for url, page in pages.items():
        if page.status != 200:
            continue
        for raw in page.jsonld_blocks:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            items: list = []
            schema_check._walk(data, "json-ld", items)  # noqa: SLF001
            for item in items:
                if item.type_name in LOCAL_TYPES:
                    found.append((url, item.properties))
    return found


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _declared_phones(pages: dict, blocks: list[tuple[str, dict]]) -> dict[str, set[str]]:
    """Phone numbers the site actually declares, by page.

    Only two sources count: a tel: link, and a telephone property in structured
    data. Both are the site stating a number. Matching digit runs in prose finds
    CVE identifiers, invoice numbers and dates instead.
    """
    phones: dict[str, set[str]] = defaultdict(set)

    for url, page in pages.items():
        if page.status != 200:
            continue
        for raw in page.tel_links:
            digits = _digits(raw)
            if 7 <= len(digits) <= 15:
                phones[url].add(digits)

    for url, properties in blocks:
        value = properties.get("telephone")
        if isinstance(value, str):
            digits = _digits(value)
            if 7 <= len(digits) <= 15:
                phones[url].add(digits)

    return phones


def _address_text(properties: dict) -> str | None:
    """A PostalAddress flattened to one comparable string, or None."""
    address = properties.get("address")
    if isinstance(address, str) and address.strip():
        return " ".join(address.split()).lower()
    if isinstance(address, dict):
        parts = [
            str(address.get(key, "")).strip()
            for key in (
                "streetAddress", "addressLocality", "addressRegion",
                "postalCode", "addressCountry",
            )
        ]
        joined = " ".join(part for part in parts if part)
        return " ".join(joined.split()).lower() or None
    return None


def check_local(pages: dict, emitted: list[F.Finding]) -> dict:
    """Module I. Reads declarations only: structured data and tel: links."""
    blocks = _local_blocks(pages)

    if not blocks:
        return {
            "active": False,
            "reason": (
                "no LocalBusiness-family structured data, so module I stays off. "
                "A street name in prose is not evidence of a local business."
            ),
        }

    phones = _declared_phones(pages, blocks)
    all_phones = {phone for values in phones.values() for phone in values}
    if len(all_phones) > 1:
        emitted.append(
            F.make(
                "local.nap_mismatch",
                sorted(phones),
                f"{len(all_phones)} different phone numbers are declared across the site: "
                + ", ".join(sorted(all_phones)[:4]),
                group="telephone",
            )
        )

    names: set[str] = set()
    addresses: set[str] = set()
    storefronts = 0

    for url, properties in blocks:
        present = {key for key in properties if not key.startswith("@")}

        name = properties.get("name")
        if isinstance(name, str) and name.strip():
            names.add(" ".join(name.split()))

        address = _address_text(properties)
        if address:
            addresses.add(address)
            storefronts += 1

        # A business with a physical address is held to the storefront list.
        # One declaring areaServed instead is a service-area business and is
        # not missing an address it never claimed to have.
        wanted = STOREFRONT_RECOMMENDED if address else COMMON_RECOMMENDED
        missing = [key for key in wanted if key not in present]
        if missing:
            kind = "storefront" if address else "service-area"
            emitted.append(
                F.make(
                    "local.localbusiness_incomplete",
                    url,
                    f"{properties.get('@type', 'LocalBusiness')} markup ({kind}) has no "
                    + ", ".join(missing),
                    group=",".join(missing),
                )
            )

    if len(names) > 1:
        emitted.append(
            F.make(
                "local.nap_mismatch",
                [url for url, _ in blocks],
                "the business name differs between markup blocks: " + ", ".join(sorted(names)),
                group="name",
            )
        )

    if len(addresses) > 1:
        emitted.append(
            F.make(
                "local.nap_mismatch",
                [url for url, _ in blocks],
                f"{len(addresses)} different addresses are declared across the site",
                group="address",
            )
        )

    emitted.append(
        F.make(
            "local.manual_checklist",
            "https://www.google.com/business/",
            "Google Business Profile and Bing Places have no API here. Check by hand that "
            "the listing name, address, phone, hours and categories match the site.",
        )
    )

    return {
        "active": True,
        "localbusiness_blocks": len(blocks),
        "storefront_blocks": storefronts,
        "declared_phones": sorted(all_phones),
        "declared_names": sorted(names),
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

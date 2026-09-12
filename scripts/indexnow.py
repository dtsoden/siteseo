"""Submit URLs to IndexNow.

IndexNow accepts ordinary pages. Google's Indexing API does not: it takes only
JobPosting and BroadcastEvent, so there is no way to push a normal page to
Google programmatically. Requesting indexing there is a button in Search
Console, by hand, roughly ten a day.

IndexNow reaches Bing, Yandex, Seznam and Naver through one endpoint. It is
free, needs no account, and proves domain control with a key file at the site
root whose contents are its own filename.

    siteseo run indexnow.py --setup     create the key file
    siteseo run indexnow.py             submit every sitemap URL
    siteseo run indexnow.py --changed   submit only what git says changed
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import httpx

ENDPOINT = "https://api.indexnow.org/IndexNow"
#: The protocol caps a single submission at 10,000 URLs.
MAX_URLS = 10_000
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def find_key(cfg) -> tuple[str | None, Path | None]:
    """The existing key, from the build output or the source root."""
    roots = [p for p in (cfg.build_path, cfg.root) if p and p.is_dir()]
    for root in roots:
        for candidate in sorted(root.glob("*.txt")):
            stem = candidate.stem
            if len(stem) < 8 or len(stem) > 128:
                continue
            if not all(c in "0123456789abcdefABCDEF-" for c in stem):
                continue
            try:
                content = candidate.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if content == stem:
                return stem, candidate
    return None, None


def create_key(cfg) -> tuple[str, Path]:
    """Write a new key file into the site's source, not its build output.

    Build output is regenerated, so a key written there disappears on the next
    build and IndexNow starts rejecting submissions.
    """
    key = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    for candidate in ("public", "static", "src"):
        folder = cfg.root / candidate
        if folder.is_dir():
            target = folder / f"{key}.txt"
            break
    else:
        target = cfg.root / f"{key}.txt"

    target.write_text(key + "\n", encoding="utf-8")
    return key, target


def sitemap_urls(cfg) -> list[str]:
    """URLs from the build's sitemap, which is what actually ships."""
    for root in (cfg.build_path, cfg.root):
        if not root or not root.is_dir():
            continue
        sitemap = root / "sitemap.xml"
        if not sitemap.is_file():
            continue
        try:
            tree = ET.fromstring(sitemap.read_bytes())
        except ET.ParseError:
            continue
        found = [n.text.strip() for n in tree.findall(".//sm:loc", SITEMAP_NS) if n.text]
        if not found:
            found = [n.text.strip() for n in tree.findall(".//loc") if n.text]
        if found:
            return found
    return []


def changed_urls(cfg) -> list[str]:
    """URLs whose files changed in the last commit, per git.

    What a deploy hook wants: telling search engines about forty unchanged pages
    on every deploy is noise, and repeated noise is how a submitter gets ignored.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(cfg.root), "diff", "--name-only", "HEAD~1", "HEAD"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []

    build = cfg.build_path
    urls: list[str] = []
    for line in proc.stdout.splitlines():
        path = (cfg.root / line.strip()).resolve()
        if path.suffix.lower() not in {".html", ".htm"}:
            continue
        base = build if (build and build in path.parents) else cfg.root
        try:
            relative = path.relative_to(base).as_posix()
        except ValueError:
            continue
        if relative.endswith("index.html"):
            url_path = "/" + relative[: -len("index.html")]
        else:
            url_path = "/" + relative[: -len(".html")]
        urls.append(cfg.origin.rstrip("/") + url_path)
    return urls


def submit(cfg, key: str, urls: list[str], *, dry_run: bool = False) -> dict:
    host = urlparse(cfg.site).netloc
    payload = {
        "host": host,
        "key": key,
        "keyLocation": f"{cfg.origin}/{key}.txt",
        "urlList": urls[:MAX_URLS],
    }
    if dry_run:
        return {"status": "dry run", "count": len(payload["urlList"]), "payload": payload}

    try:
        response = httpx.post(ENDPOINT, json=payload, timeout=60)
    except httpx.HTTPError as exc:
        return {"status": "failed", "error": str(exc), "count": len(payload["urlList"])}

    # 200 accepted, 202 accepted but the key is still being verified.
    return {
        "status_code": response.status_code,
        "status": {
            200: "accepted",
            202: "accepted, key still being validated",
            400: "bad request",
            403: "key not valid for this host",
            422: "a URL does not belong to this host, or the key does not match",
            429: "too many requests",
        }.get(response.status_code, f"unexpected {response.status_code}"),
        "count": len(payload["urlList"]),
        "key_location": payload["keyLocation"],
    }


def verify_key_live(cfg, key: str) -> tuple[bool, str]:
    """IndexNow fetches the key file itself, so it has to be reachable first."""
    url = f"{cfg.origin}/{key}.txt"
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
    except httpx.HTTPError as exc:
        return False, f"{url} could not be fetched: {exc}"
    if response.status_code != 200:
        return False, f"{url} returned {response.status_code}. Deploy it before submitting."
    if response.text.strip() != key:
        return False, f"{url} does not contain the key. It must contain exactly {key}"
    return True, f"{url} is live"


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Submit URLs to IndexNow")
    parser.add_argument("--setup", action="store_true", help="create a key file")
    parser.add_argument("--changed", action="store_true",
                        help="submit only pages changed in the last commit")
    parser.add_argument("--url", action="append", default=[], help="submit one URL")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    key, path = find_key(cfg)

    if args.setup:
        if key:
            print(f"A key already exists: {path}\nNothing to do.")
            return 0
        key, path = create_key(cfg)
        print(f"Created {path}")
        print(f"Key: {key}")
        print()
        print("Deploy the site, then submit with: siteseo run indexnow.py")
        return 0

    if not key:
        print(
            "No IndexNow key found in this site.\n"
            "Create one with: siteseo run indexnow.py --setup",
            file=sys.stderr,
        )
        return 1

    if args.url:
        urls = args.url
    elif args.changed:
        urls = changed_urls(cfg)
        if not urls:
            print("No HTML files changed in the last commit. Nothing to submit.")
            return 0
    else:
        urls = sitemap_urls(cfg)
        if not urls:
            print("No sitemap found, so there is nothing to submit.", file=sys.stderr)
            return 1

    if not args.dry_run:
        live, detail = verify_key_live(cfg, key)
        print(detail)
        if not live:
            return 1

    result = submit(cfg, key, urls, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{result['count']} URL(s): {result['status']}")
        if result.get("error"):
            print(f"  {result['error']}")
        print()
        print(
            "IndexNow reaches Bing, Yandex, Seznam and Naver. Google does not "
            "participate, and its Indexing API takes only JobPosting and "
            "BroadcastEvent pages, so ordinary pages still need Request "
            "indexing in Search Console by hand."
        )
    return 0 if result.get("status_code") in (200, 202) or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())

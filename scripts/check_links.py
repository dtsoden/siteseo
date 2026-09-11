"""Verify every source URL in the check catalog still resolves.

Every finding promises a source link. A dead one breaks that promise quietly,
and documentation sites reorganise often: Google moved its crawling
documentation to a new path during this project's first day.

Some hosts refuse automated requests with a 403 while serving the page normally
to a browser. Those are listed below rather than papered over, so the list is
short and visible and each entry says why it is there.

Exit codes: 0 everything resolves, 1 something does not, 2 the check failed.
"""

from __future__ import annotations

import concurrent.futures
import json
import sys

import httpx

import findings as F

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

#: Hosts that answer automated requests with 403 while serving browsers fine.
#: Verified by hand; a 403 from one of these is not treated as a dead link.
BOT_HOSTILE = {
    "www.w3.org": "W3C blocks automated requests; pages verified by hand",
}

TIMEOUT = 30.0
WORKERS = 8


def check(url: str) -> tuple[str, int | str, str]:
    try:
        with httpx.Client(
            follow_redirects=True, timeout=TIMEOUT, headers={"User-Agent": BROWSER_UA}
        ) as client:
            response = client.get(url)
            final = str(response.url)
            return url, response.status_code, final if final.rstrip("/") != url.rstrip("/") else ""
    except httpx.HTTPError as exc:
        return url, f"ERR {type(exc).__name__}", ""


def run() -> dict:
    urls = sorted(
        {check_.source for check_ in F.catalog().values() if check_.source.startswith("http")}
    )
    rows = []
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        for url, status, redirect in pool.map(check, urls):
            host = url.split("/")[2]
            tolerated = status == 403 and host in BOT_HOSTILE
            rows.append(
                {
                    "url": url,
                    "status": status,
                    "redirects_to": redirect,
                    "ok": status == 200 or tolerated,
                    "tolerated": tolerated,
                    "reason": BOT_HOSTILE.get(host, "") if tolerated else "",
                }
            )

    broken = [row for row in rows if not row["ok"]]
    moved = [row for row in rows if row["ok"] and row["redirects_to"]]
    return {"checked": len(rows), "rows": rows, "broken": broken, "moved": moved}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Check every catalog source URL")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = run()
    except Exception as exc:  # a failure to check is not a failure of the links
        print(f"link check could not run: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{result['checked']} source URLs checked")
        for row in result["moved"]:
            print(f"  moved  {row['url']}")
            print(f"         now {row['redirects_to']}")
        for row in result["rows"]:
            if row["tolerated"]:
                print(f"  {row['status']}    {row['url']}  ({row['reason']})")
        for row in result["broken"]:
            print(f"  BROKEN {row['status']}  {row['url']}")
        print()
        print(
            "All source links resolve."
            if not result["broken"]
            else f"{len(result['broken'])} source link(s) need updating in checks.yaml."
        )
        if result["moved"]:
            print(
                f"{len(result['moved'])} link(s) redirect. They still work, but updating "
                "checks.yaml to the final URL keeps the catalog honest."
            )

    return 1 if result["broken"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

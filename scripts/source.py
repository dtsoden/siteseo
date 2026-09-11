"""One interface over a local build directory and a live site.

Every module fetches through a Source, so the same checks run before deploy and
after. The two backends differ in one way that matters and is never hidden: a
build directory has no server, so response headers do not exist. Header-dependent
checks return UNAVAILABLE rather than passing, and the report says so.
"""

from __future__ import annotations

import mimetypes
import os
import posixpath
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator
from urllib.parse import unquote, urljoin, urlparse, urlunparse

import httpx

UNAVAILABLE = "unavailable"


class OfflineRefused(RuntimeError):
    """Raised when code tries to reach the network while SITESEO_OFFLINE is set."""

DEFAULT_UA = (
    "Mozilla/5.0 (compatible; siteseo/0.1; +https://github.com/dtsoden/siteseo)"
)

# Extensions that a static host serves as HTML pages.
PAGE_SUFFIXES = {".html", ".htm"}


@dataclass
class Hop:
    url: str
    status: int
    location: str


@dataclass
class Response:
    url: str
    status: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    final_url: str = ""
    hops: list[Hop] = field(default_factory=list)
    error: str | None = None
    headers_available: bool = True

    def __post_init__(self) -> None:
        if not self.final_url:
            self.final_url = self.url

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def is_html(self) -> bool:
        ctype = self.headers.get("content-type", "")
        if ctype:
            return "html" in ctype.lower()
        # Build mode: decide from the path.
        return Path(urlparse(self.final_url).path).suffix.lower() in PAGE_SUFFIXES or (
            urlparse(self.final_url).path.endswith("/")
        )

    def text(self) -> str:
        if not self.body:
            return ""
        ctype = self.headers.get("content-type", "")
        charset = "utf-8"
        if "charset=" in ctype:
            charset = ctype.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")

    def header(self, name: str) -> str | None:
        """Header value, or UNAVAILABLE when no server was involved."""
        if not self.headers_available:
            return UNAVAILABLE
        return self.headers.get(name.lower())


def normalise(url: str) -> str:
    """Drop the fragment and collapse an empty path to /."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, ""))


class Source:
    """Base interface. Subclasses implement fetch()."""

    #: True when responses carry real HTTP headers.
    headers_available = True
    #: Human label for reports.
    label = "source"

    def fetch(self, url: str, *, user_agent: str | None = None, method: str = "GET") -> Response:
        raise NotImplementedError

    def absolute(self, path_or_url: str) -> str:
        raise NotImplementedError

    def is_internal(self, url: str) -> bool:
        return True

    def close(self) -> None:  # pragma: no cover - trivial
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class LiveSource(Source):
    """Fetch over HTTP from the deployed site."""

    headers_available = True

    def __init__(self, origin: str, *, timeout: float = 20.0, max_hops: int = 10):
        # The gate sets SITESEO_OFFLINE. Refusing to construct a network source
        # here makes "the gate never calls out" a property of the code rather
        # than a promise in the documentation, and tests can assert it.
        if os.environ.get("SITESEO_OFFLINE"):
            raise OfflineRefused(
                "SITESEO_OFFLINE is set, so no network request may be made. "
                "This run is meant to work from build output only."
            )
        self.origin = origin.rstrip("/")
        self.label = self.origin
        self.max_hops = max_hops
        self._client = httpx.Client(
            follow_redirects=False,
            timeout=timeout,
            headers={"User-Agent": DEFAULT_UA},
            verify=True,
        )

    def absolute(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            return path_or_url
        return urljoin(self.origin + "/", path_or_url.lstrip("/"))

    def fetch(self, url: str, *, user_agent: str | None = None, method: str = "GET") -> Response:
        target = self.absolute(url)
        headers = {"User-Agent": user_agent} if user_agent else {}
        hops: list[Hop] = []
        current = target

        for _ in range(self.max_hops + 1):
            try:
                resp = self._client.request(method, current, headers=headers)
            except httpx.HTTPError as exc:
                return Response(
                    url=target,
                    status=0,
                    final_url=current,
                    hops=hops,
                    error=f"{type(exc).__name__}: {exc}",
                )

            if resp.is_redirect and "location" in resp.headers:
                location = urljoin(current, resp.headers["location"])
                hops.append(Hop(url=current, status=resp.status_code, location=location))
                if any(hop.url == location for hop in hops) or location == current:
                    return Response(
                        url=target,
                        status=resp.status_code,
                        headers={k.lower(): v for k, v in resp.headers.items()},
                        final_url=location,
                        hops=hops,
                        error="redirect loop",
                    )
                current = location
                continue

            return Response(
                url=target,
                status=resp.status_code,
                body=resp.content,
                headers={k.lower(): v for k, v in resp.headers.items()},
                final_url=current,
                hops=hops,
            )

        return Response(
            url=target,
            status=0,
            final_url=current,
            hops=hops,
            error=f"more than {self.max_hops} redirects",
        )

    def close(self) -> None:
        self._client.close()


class BuildSource(Source):
    """Read from a local build directory the way a static host would serve it.

    Resolution order for a request path, matching how Netlify, Vercel,
    Cloudflare Pages and GitHub Pages serve static output:

        /about/      -> about/index.html
        /about       -> about.html, then about/index.html
        /            -> index.html

    There is no server, so `headers_available` is False and every
    header-dependent check reports UNAVAILABLE instead of passing.
    """

    headers_available = False

    def __init__(self, build_dir: Path, origin: str):
        self.root = Path(build_dir).resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(f"build_dir does not exist: {self.root}")
        self.origin = origin.rstrip("/")
        self.label = str(self.root)

    def absolute(self, path_or_url: str) -> str:
        if path_or_url.startswith(("http://", "https://")):
            return path_or_url
        return urljoin(self.origin + "/", path_or_url.lstrip("/"))

    def _candidates(self, path: str) -> list[Path]:
        clean = unquote(urlparse(path).path)
        clean = posixpath.normpath("/" + clean.lstrip("/"))
        if clean == "/":
            return [self.root / "index.html"]
        relative = clean.lstrip("/")
        if path.rstrip("?").endswith("/"):
            return [self.root / relative / "index.html"]
        return [
            self.root / relative,
            self.root / f"{relative}.html",
            self.root / relative / "index.html",
        ]

    def _safe(self, candidate: Path) -> Path | None:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(self.root)
        except (ValueError, OSError):
            return None
        return resolved

    def is_internal(self, url: str) -> bool:
        absolute = self.absolute(url)
        return absolute.startswith(self.origin + "/") or absolute == self.origin

    def fetch(self, url: str, *, user_agent: str | None = None, method: str = "GET") -> Response:
        target = self.absolute(url)

        # An external URL has no file in the build. Looking one up locally would
        # invent a 404, and reaching for it over the network would put a request
        # in the gate, which must make none. Report it as not checked instead.
        if not self.is_internal(target):
            return Response(
                url=target,
                status=0,
                final_url=target,
                headers_available=False,
                error="external URL, not checked while auditing build output",
            )

        path = urlparse(target).path or "/"

        for candidate in self._candidates(path):
            resolved = self._safe(candidate)
            if resolved is None or not resolved.is_file():
                continue
            body = b"" if method == "HEAD" else resolved.read_bytes()
            guessed, _ = mimetypes.guess_type(resolved.name)
            return Response(
                url=target,
                status=200,
                body=body,
                headers={"content-type": guessed or "application/octet-stream"},
                final_url=target,
                headers_available=False,
            )

        return Response(
            url=target,
            status=404,
            final_url=target,
            headers_available=False,
            error="not present in build output",
        )

    def local_path(self, url: str) -> Path | None:
        """Where a URL's file actually lives on disk, for size and format checks."""
        path = urlparse(self.absolute(url)).path or "/"
        for candidate in self._candidates(path):
            resolved = self._safe(candidate)
            if resolved is not None and resolved.is_file():
                return resolved
        return None

    def walk_pages(self) -> Iterator[tuple[str, Path]]:
        """Every HTML file in the build, as (url, path)."""
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in PAGE_SUFFIXES:
                continue
            relative = path.relative_to(self.root).as_posix()
            if relative.endswith("index.html"):
                url_path = "/" + relative[: -len("index.html")]
            else:
                url_path = "/" + relative
            yield self.absolute(url_path), path


def open_source(cfg, *, live: bool = False) -> Source:
    """Pick the backend a run should use.

    Build output is the default when it exists, because catching a problem
    before deploy is the point. `live=True` forces HTTP.
    """
    if not live:
        build = cfg.build_path
        if build is not None and build.is_dir():
            return BuildSource(build, cfg.origin)
    return LiveSource(cfg.origin)

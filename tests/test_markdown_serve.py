"""Serving exported Markdown, and the optional llms.txt index.

The JavaScript handlers run under Node with each platform's request objects
faked, so the negotiation logic is tested rather than trusted. Those tests skip
on a machine with no Node. The nginx handler was tested against nginx itself in
Docker when it was written; that needs a daemon, so it is not repeated here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import config
import markdown_export as M
import markdown_serve as S


def _cfg(root: Path, host: str = "other") -> config.Config:
    (root / "dist").mkdir(exist_ok=True)
    return config.parse(
        {"site": "https://www.x.example", "build_dir": "dist", "host": host}, root, where="test"
    )


# ------------------------------------------------------- plans


@pytest.mark.parametrize("host", S.HOSTS)
def test_every_host_renders_without_placeholders(tmp_path, host):
    cfg = _cfg(tmp_path)
    for change in S.changes(cfg, S.plan(cfg, host)):
        assert "{{" not in change.content, change.path
        if change.path.suffix in {".js", ".mjs"}:
            assert "function markdownCandidates" in change.content


def test_worker_route_uses_the_site_host_and_zone(tmp_path):
    cfg = _cfg(tmp_path)
    wrangler = next(c for c in S.changes(cfg, S.plan(cfg, "cloudflare-worker"))
                    if c.path.name == "wrangler.jsonc")
    assert '"pattern": "www.x.example/*", "zone_name": "x.example"' in wrangler.content


def test_host_defaults_to_siteseo_yaml(tmp_path):
    cfg = _cfg(tmp_path, host="netlify")
    assert S.plan(cfg).host == "netlify"


@pytest.mark.parametrize("host", ["github-pages", "other"])
def test_hosts_that_cannot_negotiate_say_so(tmp_path, host, capsys):
    cfg = _cfg(tmp_path, host=host)
    assert S.main(cfg) == 2
    assert "--serve" in capsys.readouterr().out


def test_nothing_is_written_without_apply_and_nothing_is_overwritten(tmp_path, capsys):
    cfg = _cfg(tmp_path, host="cloudflare-pages")
    target = tmp_path / "functions" / "_middleware.js"

    assert S.main(cfg) == 0
    assert not target.exists()
    assert "Nothing has been written" in capsys.readouterr().out

    assert S.main(cfg, apply=True) == 0
    written = target.read_text(encoding="utf-8")
    assert "export async function onRequest" in written

    target.write_text("// my own middleware\n", encoding="utf-8")
    assert S.main(cfg, apply=True) == 0
    assert target.read_text(encoding="utf-8") == "// my own middleware\n"
    assert "Not overwriting" in capsys.readouterr().out


# ------------------------------------------------------- the handlers, under Node

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="Node is not installed")

DRIVER = r"""
import { pathToFileURL } from "node:url";
const [kind, target] = process.argv.slice(2);
const mod = await import(pathToFileURL(target).href);
const files = {
  "/index.md": ["# Home", "text/markdown"],
  "/about/index.md": ["# About", "text/markdown"],
  "/blog.md": ["# Blog", "text/markdown"],
};
// A static host with a single-page fallback: anything missing is the home page.
const serve = (url) => {
  const hit = files[new URL(url).pathname];
  return hit
    ? new Response(hit[0], { headers: { "content-type": hit[1] } })
    : new Response("<html>page</html>", { headers: { "content-type": "text/html" } });
};
globalThis.fetch = async (input) => serve(input instanceof Request ? input.url : String(input));

async function call(request) {
  if (kind === "pages") {
    return mod.onRequest({ request, env: { ASSETS: { fetch: async (u) => serve(String(u)) } },
                           next: async () => serve(request.url) });
  }
  if (kind === "worker") return mod.default.fetch(request);
  const res = await mod.default(request, {});
  return res === undefined ? serve(request.url) : res;
}

const cases = [["/", "text/markdown"], ["/", "text/html"], ["/about", "text/markdown"],
  ["/about/", "text/markdown"], ["/blog.html", "TEXT/MARKDOWN"], ["/missing", "text/markdown"],
  ["/style.css", "text/markdown"], ["/about/index.md", ""], ["/blog.md", ""]];
const out = {};
for (const [path, accept] of cases) {
  const headers = accept ? { accept } : {};
  const res = await call(new Request("https://x.example" + path, { headers }));
  out[`${path} ${accept}`] = { type: res.headers.get("content-type"), vary: res.headers.get("vary"),
    link: res.headers.get("link"), body: await res.text() };
}
console.log(JSON.stringify(out));
"""


def _run(tmp_path: Path, kind: str, host: str, name: str) -> dict:
    cfg = _cfg(tmp_path)
    change = next(c for c in S.changes(cfg, S.plan(cfg, host)) if c.path.name == name)
    handler = tmp_path / f"{kind}.mjs"
    handler.write_text(change.content, encoding="utf-8")
    driver = tmp_path / "driver.mjs"
    driver.write_text(DRIVER, encoding="utf-8")
    proc = subprocess.run([NODE, str(driver), kind, str(handler)],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _check_negotiation(out: dict, *, direct_md: bool) -> None:
    for request, body in (("/ text/markdown", "# Home"), ("/about text/markdown", "# About"),
                          ("/about/ text/markdown", "# About"), ("/blog.html TEXT/MARKDOWN", "# Blog")):
        assert out[request]["body"] == body, request
        assert out[request]["type"] == "text/markdown; charset=utf-8", request
        assert "Accept" in (out[request]["vary"] or ""), request

    assert out["/ text/html"]["body"] == "<html>page</html>"
    # The single-page fallback answers /missing.md with HTML; that must not pass as Markdown.
    assert out["/missing text/markdown"]["body"] == "<html>page</html>"
    assert out["/style.css text/markdown"]["vary"] is None
    if direct_md:
        assert out["/about/index.md "]["link"] == '<https://x.example/about/>; rel="canonical"'
        assert out["/blog.md "]["link"] == '<https://x.example/blog>; rel="canonical"'


@needs_node
def test_cloudflare_pages_middleware_negotiates(tmp_path):
    out = _run(tmp_path, "pages", "cloudflare-pages", "_middleware.js")
    _check_negotiation(out, direct_md=True)
    assert out["/ text/html"]["vary"] == "Accept"


@needs_node
def test_cloudflare_worker_negotiates(tmp_path):
    _check_negotiation(_run(tmp_path, "worker", "cloudflare-worker", "index.js"), direct_md=True)


@needs_node
def test_netlify_edge_function_negotiates(tmp_path):
    _check_negotiation(_run(tmp_path, "netlify", "netlify", "siteseo-markdown.js"), direct_md=False)


# ------------------------------------------------------- llms.txt


def _doc(title: str, description: str = "") -> str:
    meta = f'<meta name="description" content="{description}">' if description else ""
    return f"<html><head><title>{title}</title>{meta}</head><body><main><h1>{title}</h1></main></body></html>"


def _site(root: Path, files: dict[str, str]) -> config.Config:
    for relative, text in files.items():
        path = root / "dist" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return config.parse({"site": "https://x.example", "build_dir": "dist"}, root, where="test")


def test_llms_txt_is_off_unless_asked_for(tmp_path):
    cfg = _site(tmp_path, {"index.html": _doc("Home")})
    M.export(cfg)
    assert not (tmp_path / "dist" / "llms.txt").exists()


def test_llms_txt_lists_every_exported_page(tmp_path):
    cfg = _site(tmp_path, {
        "index.html": _doc("Demo Site", "What this site is"),
        "about/index.html": _doc("About", "Who we are"),
        "blog.html": _doc("Blog"),
    })
    assert M.export(cfg, llms_txt=True).llms_txt == "written"
    assert (tmp_path / "dist" / "llms.txt").read_text(encoding="utf-8") == (
        "# Demo Site\n\n> What this site is\n\n## Pages\n\n"
        "- [Demo Site](https://x.example/index.md): What this site is\n"
        "- [About](https://x.example/about/index.md): Who we are\n"
        "- [Blog](https://x.example/blog.md)\n\n"
        f"{M.LLMS_MARKER}\n"
    )
    assert M.export(cfg, llms_txt=True).llms_txt == "unchanged"


def test_a_hand_written_llms_txt_is_left_alone(tmp_path):
    cfg = _site(tmp_path, {"index.html": _doc("Home"), "llms.txt": "# Mine\n"})
    assert M.export(cfg, llms_txt=True).llms_txt.startswith("skipped")
    assert (tmp_path / "dist" / "llms.txt").read_text(encoding="utf-8") == "# Mine\n"

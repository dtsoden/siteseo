// Shared by every generated handler. Kept in one place so each host behaves the
// same way: the .md file that /siteseo markdown wrote next to a page is served
// when a request asks for text/markdown, and HTML is served otherwise.

// Where the Markdown for a request path would be, in the order to try.
//   /about/      -> /about/index.md
//   /blog.html   -> /blog.md
//   /about       -> /about.md, then /about/index.md
// Paths that already name a file, such as .css, .png or .md, are never negotiated.
function markdownCandidates(pathname) {
  if (pathname.endsWith(".md")) return [];
  if (pathname.endsWith("/")) return [pathname + "index.md"];
  if (pathname.endsWith(".html")) return [pathname.slice(0, -5) + ".md"];
  const last = pathname.split("/").pop();
  if (/\.[a-z0-9]+$/i.test(last)) return [];
  return [pathname + ".md", pathname + "/index.md"];
}

function wantsMarkdown(request) {
  const method = request.method;
  return (method === "GET" || method === "HEAD") &&
    /text\/markdown/i.test(request.headers.get("accept") || "");
}

// A host serving a single-page fallback answers a missing file with the home
// page's HTML and a 200. That is not Markdown, so it does not count as found.
function isMarkdownFile(response) {
  return response.ok && !(response.headers.get("content-type") || "").startsWith("text/html");
}

// The page a .md file belongs to, for a rel="canonical" Link header on direct
// .md requests, so search engines credit the HTML page rather than the copy.
//   /about/index.md -> /about/      /blog.md -> /blog
function canonicalPage(pathname) {
  return pathname.endsWith("/index.md")
    ? pathname.slice(0, -"index.md".length)
    : pathname.slice(0, -".md".length);
}

function asMarkdown(response, canonical) {
  const out = new Response(response.body, response);
  out.headers.set("Content-Type", "text/markdown; charset=utf-8");
  out.headers.append("Vary", "Accept");
  if (canonical) out.headers.set("Link", `<${canonical}>; rel="canonical"`);
  return out;
}

function withVary(response) {
  const out = new Response(response.body, response);
  out.headers.append("Vary", "Accept");
  return out;
}

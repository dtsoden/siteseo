// Written by siteseo: /siteseo markdown --setup --serve cloudflare-pages
// Cloudflare Pages Function that serves Markdown for Accept: text/markdown.
// Every request now runs this function, and function requests count against the
// Workers free quota of 100,000 a day.

// {{HELPERS}}

export async function onRequest(context) {
  const { request, env, next } = context;
  const url = new URL(request.url);

  if (url.pathname.endsWith(".md")) {
    const response = await next();
    return response.ok ? asMarkdown(response, url.origin + canonicalPage(url.pathname)) : response;
  }

  const candidates = markdownCandidates(url.pathname);
  if (candidates.length && wantsMarkdown(request)) {
    for (const path of candidates) {
      const response = await env.ASSETS.fetch(new URL(path, url));
      if (isMarkdownFile(response)) return asMarkdown(response);
    }
  }

  // _headers rules are not applied to responses from Functions, so Vary is set here.
  const response = await next();
  return candidates.length ? withVary(response) : response;
}

// Written by siteseo: /siteseo markdown --setup --serve cloudflare-worker
// Cloudflare Worker on a route in front of any origin, for sites whose DNS is
// proxied through Cloudflare but hosted elsewhere. fetch(request) goes to the
// origin without running this Worker again. Free plan: 100,000 requests a day.

// {{HELPERS}}

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname.endsWith(".md")) {
      const response = await fetch(request);
      return response.ok ? asMarkdown(response, url.origin + canonicalPage(url.pathname)) : response;
    }

    const candidates = markdownCandidates(url.pathname);
    if (candidates.length && wantsMarkdown(request)) {
      for (const path of candidates) {
        const response = await fetch(new Request(new URL(path, url), request));
        if (isMarkdownFile(response)) return asMarkdown(response);
      }
    }

    const response = await fetch(request);
    return candidates.length ? withVary(response) : response;
  },
};

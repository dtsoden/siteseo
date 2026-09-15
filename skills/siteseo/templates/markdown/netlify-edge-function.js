// Written by siteseo: /siteseo markdown --setup --serve netlify
// Netlify Edge Function that serves Markdown for Accept: text/markdown. It runs
// only for requests carrying that header, before static files are served.

// {{HELPERS}}

export default async (request) => {
  // config.header already limits this to Markdown requests. Checking again keeps
  // the function correct if that match ever differs, for example on letter case.
  if (!wantsMarkdown(request)) return;
  const url = new URL(request.url);
  for (const path of markdownCandidates(url.pathname)) {
    // A fetch to the same site starts a new request chain, and excludedPath
    // keeps that chain from running this function again.
    const response = await fetch(new URL(path, url));
    if (isMarkdownFile(response)) {
      const headers = new Headers(response.headers);
      headers.set("Content-Type", "text/markdown; charset=utf-8");
      headers.append("Vary", "Accept");
      return new Response(request.method === "HEAD" ? null : response.body, { status: 200, headers });
    }
  }
  // Returning nothing lets Netlify serve the HTML as usual.
};

export const config = {
  path: "/*",
  excludedPath: ["/*.md"],
  header: { accept: "text/markdown" },
};

// Written by siteseo: /siteseo markdown --setup --serve vercel
// Vercel Routing Middleware that serves Markdown for Accept: text/markdown.
// vercel.json rewrites cannot do this: Vercel serves an existing file before any
// rewrite, and every page exists as a file. Needs "@vercel/functions" in
// package.json. Test on a preview deployment before production.

import { next, rewrite } from "@vercel/functions";

// {{HELPERS}}

export const config = {
  matcher: ["/((?!.*\\.(?:css|js|mjs|png|jpe?g|gif|svg|webp|avif|ico|txt|xml|json|md|woff2?)$).*)"],
};

export default async function middleware(request) {
  const url = new URL(request.url);
  if (wantsMarkdown(request)) {
    for (const path of markdownCandidates(url.pathname)) {
      // A rewrite cannot tell whether its target exists, so check first and fall
      // back to the HTML rather than answering with a 404.
      const probe = await fetch(new URL(path, url), { method: "HEAD" });
      if (isMarkdownFile(probe)) {
        return rewrite(new URL(path, url), { headers: { Vary: "Accept" } });
      }
    }
  }
  return next({ headers: { Vary: "Accept" } });
}

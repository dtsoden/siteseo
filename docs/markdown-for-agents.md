[Docs home](README.md) / Markdown for agents

# Markdown for agents, without paying for it

Level 3 asks for Markdown when an agent sends `Accept: text/markdown`.
Cloudflare does this at its edge on the Pro plan and up: it fetches your HTML,
converts it, and caches the result. `/siteseoai markdown` does the same work at
build time for nothing, on any host.

```
/siteseoai markdown                                   after every build
/siteseoai markdown --setup                           once, shows the host rule
/siteseoai markdown --setup --serve netlify --apply   writes it
```

The first command reads your build output and writes a `.md` file next to every
page, keeping the main content and dropping navigation, headers, footers and
scripts. Each file opens with the page's title, description and canonical URL
and ends with its JSON-LD, the same shape Cloudflare produces. Each page gets a
`<link rel="alternate" type="text/markdown">` tag pointing at its copy, so an
agent that never sends the header can still find it. Pages carrying noindex are
skipped, a `.md` file you wrote yourself is never touched, and copies of pages
that no longer exist are removed. Put it in your build script after the build
itself, because the Markdown is only as fresh as the last run.

Plain files cannot read a request header, so the host needs one small rule that
hands out the `.md` when an agent asks. `--setup` generates it and writes nothing
until `--apply`:

| `--serve` | What it writes | Cost |
| --- | --- | --- |
| `cloudflare-pages` | `functions/_middleware.js` | Workers free quota, 100,000 requests a day |
| `cloudflare-worker` | a Worker for any host whose DNS is proxied through Cloudflare | same free quota |
| `netlify` | an edge function | Netlify plan limits |
| `vercel` | routing middleware | Vercel plan limits; try it on a preview first |
| `nginx` | a config snippet to merge into your server, tested against nginx in Docker | free |

GitHub Pages cannot vary a response on a request header at all. The Markdown
files and link tags still help there, and a domain proxied through Cloudflare
can put the Worker in front. Once deployed, `/siteseoai agents --live` confirms
agents get Markdown.

There is no RFC for a sitemap of Markdown pages. The nearest thing is
[llms.txt](https://llmstxt.org), a community convention, and `--llms-txt` writes
one listing every exported page. It is off by default for the reasons given
in
[what siteseoai does not check](not-checked.md#no-llmstxt-scoring).

---

Previous: [The pre-deploy gate](gate.md) | Next: [Where your data lives](data.md)

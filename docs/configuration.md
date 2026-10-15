[Docs home](README.md) / Configuration

# Configuration

One file per site, committed.

```yaml
site: https://example.com

# auto, astro, next, hugo, eleventy, plain-html, other
stack: auto

# Directory holding built HTML. Auditing this catches problems before deploy.
build_dir: dist

# netlify, vercel, cloudflare-pages, github-pages, other
host: netlify

# One sample URL per page template. Performance tests run against these.
templates:
  - /
  - /blog/sample-post/
  - /about/

# What you want AI crawlers to be able to do. siteseoai flags any mismatch between
# this and what robots.txt and your CDN actually do, in both directions.
ai_policy:
  search_and_user_fetch: allow   # OAI-SearchBot, ChatGPT-User, Claude-SearchBot,
                                 # Claude-User, PerplexityBot, Perplexity-User
  training: allow                # GPTBot, ClaudeBot, Google-Extended,
                                 # Applebot-Extended, CCBot

# Questions a real customer would type. Used by `siteseoai track`.
prompts:
  - "how do I keep AI crawlers from being blocked by my CDN"

competitors:
  - competitor-one.com

budget:
  monthly_usd: 0

# Which agent standards apply: content, api or commerce. Content-Signal values
# follow ai_policy unless you set them here.
agent_readiness:
  profile: content
  content_signals:
    ai_train: no

secrets: env

# Optional. The logo shown on reports. Without it, siteseoai uses the logo your
# homepage declares, a logo image in its header, or its site icon.
report_logo: public/logo.svg
```

Secrets never go in this file. It names them; the values live in your operating
system's vault or your environment. `doctor` reports which names resolve on the
current machine and never prints a value. A test asserts that no credential
pattern appears anywhere in the repository.

---

Previous: [Commands](commands.md) | Next: [Findings and fixes](findings-and-fixes.md)

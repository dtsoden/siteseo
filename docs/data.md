[Docs home](README.md) / Where your data lives

# Where your data lives

Everything a site needs travels with the site repository and is committed.

```
<site repo>/
  siteseoai.yaml
  .siteseoai/history/    dated JSON snapshots
  .siteseoai/reports/    dated reports: Markdown, a styled HTML page, and PDF on request
  .siteseoai/imports/    manual CSV exports
```

This is the point. Clone the repository on another machine and the trend is
already there. Nothing depends on a cache directory that exists in one home
folder on one laptop, which is how most tooling loses your history.

Drop CSV exports into `.siteseoai/imports/` for the data that has no API:
`bing-ai/` for Bing AI Performance exports, `backlinks/` for Search Console or
Ahrefs link exports, `logs/` for access logs from your host or CDN. The
[Bing](setup/07-bing.md#the-ai-performance-report) and
[Paid keys](setup/08-paid-keys.md#keyword-and-serp-research-dataforseo) pages
say what goes in the first two.

A site set up before the rename from siteseo has `siteseo.yaml` and a
`.siteseo/` folder instead. Both keep working until you rename them, and
[Install](setup/01-install.md#moving-from-siteseo) says how.

---

Previous: [Markdown for agents](markdown-for-agents.md) | Next: [What it checks](checks.md)

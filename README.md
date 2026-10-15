# siteseo

Search and AI search readiness auditing for sites you own, as a Claude Code
plugin. It runs against a local build directory or a live URL, puts raw evidence
and a source link behind every finding, keeps search health and AI access as two
separate scores, and gates deploys without spending a cent. It also places the
site on the agent readiness ladder Cloudflare publishes, reported beside those
two scores and never inside them.

It is not a competitor intelligence suite. It will not tell you how much traffic
someone else's domain gets, because nobody can measure that from outside. What it
does is audit properties you control using your own build output, your own
Search Console and Bing data, and free public APIs, then let you buy outside data
per request when you actually want it.

## Quick start

In Claude Code:

```
/plugin marketplace add dtsoden/siteseo
/plugin install siteseo@dtsoden-siteseo
/siteseo setup
/siteseo doctor
```

Then open any site repository and type `/siteseo`.
[Install](docs/setup/01-install.md) has the prerequisites and how to update,
and [your first report](docs/first-report.md) says what happens next.

## Documentation

The [documentation](docs/README.md) starts with a menu of every page.

Setup, checked against each vendor's documentation on 2026-10-14:

- [Setup guide](docs/setup/README.md): what each step adds and what it costs
- [Install](docs/setup/01-install.md)
- [Storing secrets](docs/setup/02-secrets.md)
- [Google Cloud](docs/setup/03-google-cloud.md)
- [Search Console](docs/setup/04-search-console.md)
- [Google Analytics](docs/setup/05-analytics.md)
- [PageSpeed and CrUX](docs/setup/06-pagespeed.md)
- [Bing Webmaster Tools](docs/setup/07-bing.md)
- [Paid keys](docs/setup/08-paid-keys.md)
- [Troubleshooting](docs/setup/troubleshooting.md)

Using siteseo:

- [Your first report](docs/first-report.md)
- [Commands](docs/commands.md)
- [Configuration](docs/configuration.md)
- [Findings and fixes](docs/findings-and-fixes.md)
- [The pre-deploy gate](docs/gate.md)
- [Markdown for agents](docs/markdown-for-agents.md)
- [Where your data lives](docs/data.md)

How it works:

- [What it checks](docs/checks.md)
- [Agent readiness](docs/agent-readiness.md)
- [What it does not check](docs/not-checked.md)
- [Staying current](docs/staying-current.md)
- [What siteseo does not cover](docs/extending.md)

## Credits

MIT licensed. Built on two MIT projects, both pinned and credited in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md):

- [addyosmani/web-quality-skills](https://github.com/addyosmani/web-quality-skills)
  for Core Web Vitals and performance guidance, vendored as reference material.
- [agricidaniel/claude-seo](https://github.com/agricidaniel/claude-seo) for the
  cross-platform launcher discovery approach that `scripts/siteseo` adapts.

The robots evaluator is written rather than borrowed. Python's
`urllib.robotparser` returns the first matching rule instead of the most specific
one, so its answer changes when the same two rules are written in the other
order. RFC 9309 says the longer pattern wins regardless of order, and that
difference decides whether a crawler is reported as blocked.
`tests/test_robots_rfc9309.py` documents the divergence and will fail if a future
Python fixes it.

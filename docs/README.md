# siteseoai documentation

Every page links back here at the top and to the page before and after it at
the bottom, so you can read straight through or jump to what you need.

## Setup

The [setup guide](setup/README.md) explains what each step adds, what it costs
and what has to exist before you start. Only the first page is required.

1. [Install](setup/01-install.md): the plugin and its Python environment.
2. [Storing secrets](setup/02-secrets.md): where siteseoai reads keys from.
3. [Google Cloud](setup/03-google-cloud.md): a project, a service account and
   the four APIs siteseoai calls.
4. [Search Console](setup/04-search-console.md): give the service account
   access to each site.
5. [Google Analytics](setup/05-analytics.md): give it access to your GA4
   account.
6. [PageSpeed and CrUX](setup/06-pagespeed.md): an API key for performance data.
7. [Bing Webmaster Tools](setup/07-bing.md): Bing data and Copilot citations.
8. [Paid keys](setup/08-paid-keys.md): optional AI citation tracking and keyword
   research, with a spending cap, and why a Claude subscription is the cheaper
   way to run siteseoai.

[Troubleshooting](setup/troubleshooting.md) covers the errors that cost real
time during setup, with the exact message each one shows.

## Using siteseoai

- [Your first report](first-report.md): what `/siteseoai` does the first time you
  run it in a site repository.
- [Commands](commands.md): every `/siteseoai` command, and running the scripts
  without Claude.
- [Configuration](configuration.md): the `siteseoai.yaml` file each site keeps.
- [Findings and fixes](findings-and-fixes.md): how findings are ranked, the
  brief for whoever maintains the site, and what fix mode will and won't write.
- [The pre-deploy gate](gate.md): a free check before every deploy, as a git
  hook or in GitHub Actions.
- [Markdown for agents](markdown-for-agents.md): serving Markdown to AI agents
  at build time, on any host.
- [Where your data lives](data.md): the folders siteseoai keeps in each site
  repository.

## How it works

- [What it checks](checks.md): the 168 checks across fourteen modules, and why
  search health and AI access stay two separate scores.
- [Agent readiness](agent-readiness.md): module O and the readiness ladder
  Cloudflare publishes.
- [What it does not check](not-checked.md): what is left out on purpose, and
  why.
- [Staying current](staying-current.md): how pinned code and reference data are
  kept up to date.
- [What siteseoai does not cover](extending.md): measurements that would need a
  paid service or an unofficial interface, and how a fork could add them.

---

Next: [Setup guide](setup/README.md)

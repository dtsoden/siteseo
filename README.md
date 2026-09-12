# siteseo

Search and AI search readiness auditing for sites you own, as a Claude Code
plugin. It runs against a local build directory or a live URL, puts raw evidence
and a source link behind every finding, keeps search health and AI access as two
separate scores, and gates deploys without spending a cent.

It is not a competitor intelligence suite. It will not tell you how much traffic
someone else's domain gets, because nobody can measure that from outside. What it
does is audit properties you control using your own build output, your own
Search Console and Bing data, and free public APIs, then let you buy outside data
per request when you actually want it.

## Install

Two commands on any machine, then two to check it works.

```
/plugin marketplace add dtsoden/siteseo
/plugin install siteseo
/siteseo setup
/siteseo doctor
```

`setup` builds an isolated Python environment with uv. It lives outside the
plugin directory, so a plugin update does not destroy it, and it is keyed by a
hash of the pinned requirements, so changing a dependency rebuilds rather than
silently mismatching. Nothing installs into your system or user Python.

A healthy `doctor` looks like this. The missing keys are normal: every one of
them is optional, and a missing key shrinks a run rather than failing it.

```
Runtime
  ok   bootstrap Python 3.11.9 on win32
  ok   uv found
  ok   isolated environment
  MISS Chromium  (module A rendered-DOM check will be skipped)

Secrets on this machine (names only, values are never read here)
  MISS SITESEO_PAGESPEED_API_KEY
       unlocks: PageSpeed Insights and CrUX (module D)

Reference data freshness
  ok   ai-bots.yaml  verified 2026-09-11 (0 days ago)
  ok   checks.yaml   verified 2026-09-11 (0 days ago)

Ready to audit.
```

Then, in any site repository:

```
/siteseo init      writes a starter siteseo.yaml
/siteseo audit     audits your build output
```

Updating later is `/plugin update siteseo`. The test suite runs on Windows, macOS
and Linux, because a tool that installs on one of them is not portable.

## Connecting Google, once

Everything above works with no account and no key. Connecting Google adds the
half a crawler cannot see: which queries you actually rank for, which pages earn
clicks, and whether AI assistants send anyone. It is free, and it is what turns
the audit from a list of defects into a ranked list of what to fix first.

One service account covers both Search Console and Analytics.

**1. Make a project and a service account.** In
[Google Cloud Console](https://console.cloud.google.com), create a project, then
IAM and Admin, Service Accounts, Create. When it asks for a role, skip it: project
roles have nothing to do with Search Console or Analytics access. On the finished
account open Keys, Add Key, JSON, and download the file.

Copy the account's email. It looks like
`something@your-project.iam.gserviceaccount.com`.

**2. Enable the two APIs** in the same project. Both free.

- Search Console API: `console.cloud.google.com/apis/library/searchconsole.googleapis.com`
- Analytics Data API: `console.cloud.google.com/apis/library/analyticsdata.googleapis.com`

**3. Grant the account access, in the products themselves.** This is the step
people miss. The key authenticates; it does not authorise.

- Search Console, Settings, Users and permissions, Add user, paste the email,
  Full or Restricted. This is per property.
- Google Analytics, Admin, **Account** column, **Account access management**, add
  the email as Viewer. Done at account level it covers every property under that
  account at once. Untick "Notify new users by email" first, or it fails.

**4. Store the path, not the file contents.**

Put the JSON key somewhere outside any repository. Then:

```
aihsm put SITESEO_GSC_SERVICE_ACCOUNT
```

and paste the **path** to the file when prompted.

[aihsm](https://github.com/dtsoden/aihsm) keeps secrets in your operating
system's credential vault, Windows Credential Manager, macOS Keychain or Linux
Secret Service, and injects them into a child process rather than printing them.
siteseo's launcher runs every bundled tool through it, so a value reaches the
code that needs it and never reaches a log, a transcript or a file.

Use whatever secret storage you already trust. siteseo reads plain environment
variables, so any of these work:

- **aihsm**, if you want the OS vault and nothing to configure.
- **A password manager** with a CLI, 1Password's `op run` or Bitwarden's `bw`,
  which inject the same way.
- **A cloud secret manager**, AWS Secrets Manager, Azure Key Vault, Google Secret
  Manager, if you already run one.
- **A plain environment variable**, exported in your shell profile. Least
  protected, but honest about it, and better than a file in a repo.

The only requirement is that `SITESEO_GSC_SERVICE_ACCOUNT` holds the path to the
key file by the time siteseo runs.

**Wherever you put it, keep the key outside every repository.** A downloaded key
is named after your project plus a random suffix, `my-project-8f3a91c2e4d7.json`,
which no gitignore pattern predicts. That file is one `git add -A` away from
being public, and a published service account key is worth rotating immediately.
siteseo's own repo denies every JSON file at its root for this exact reason, and
its test suite fails if a credential pattern appears anywhere in the tree.

**5. Check it.**

```
/siteseo doctor
```

The line for `SITESEO_GSC_SERVICE_ACCOUNT` should read `ok`. Then:

```
/siteseo pull
```

Search Console should report clicks and impressions, Analytics should report
sessions.

### Four things that will waste your afternoon

Every one of these cost real time during setup, and none of them is in Google's
own documentation in a place you would find first.

**"Failed to register users" when adding the account to Analytics.** Untick
**Notify new users by email** before clicking Add. It is ticked by default, a
service account has no mailbox, the notification fails, and it takes the whole
operation down with it. The error says nothing about email.

**Analytics access can be granted once for every property.** Use **Admin,
Account column, Account access management**, not the Property column next to it.
Account-level access flows down to every property underneath. If your sites span
several GA accounts, it is once per account, not once per property.

**Search Console has no equivalent, and will not get one.** Access is per
property, added under Settings, Users and permissions. The one shortcut is a
Domain property, which covers every subdomain and both http and https at once.
For separate domains, expect to add the email once per site.

**Enabling an API and granting access are different things, and you need both.**
A 403 saying *"has not been used in project N before or it is disabled"* means
step 2, the API is off. A 403 saying *"User does not have sufficient
permission"* means step 3, the account is not a user on that property. The first
is fixed in Cloud Console, the second inside Search Console or Analytics. They
look alike and are not.

### Optional keys

Each unlocks one module and each is independent. A missing key shrinks a run
rather than failing it.

| Name | Unlocks | Cost |
| --- | --- | --- |
| `SITESEO_GSC_SERVICE_ACCOUNT` | Search Console and Analytics | free |
| `SITESEO_PAGESPEED_API_KEY` | PageSpeed Insights and CrUX | free |
| `SITESEO_BING_API_KEY` | Bing Webmaster data | free |
| `SITESEO_ANTHROPIC_API_KEY` | AI citation tracking | per call |
| `SITESEO_OPENAI_API_KEY` | AI citation tracking | per call |
| `SITESEO_PERPLEXITY_API_KEY` | AI citation tracking | per call |
| `SITESEO_DATAFORSEO_LOGIN` and `_PASSWORD` | keyword and competitor research | per request |

## What it checks

126 checks across thirteen modules. Every one is declared in
`skills/siteseo/reference/checks.yaml` with its severity, which score it counts
against, the rule, a source URL backing that rule, the fix, and whether the fix
can be applied automatically. 46 are automatically fixable.

| Module | Area | Checks |
| --- | --- | --- |
| A | Crawl and indexability | 43 |
| B | On-page | 24 |
| C | Structured data | 9 |
| D | Performance | 9 |
| E | AI crawler access | 8 |
| F | Content quality | 9 |
| G | Internal linking | 5 |
| H | International | 5 |
| I | Local | 3 |
| J | Search performance data | 4 |
| K | AI visibility | 4 |
| L | Research, paid | 1 |
| M | Backlinks | 2 |
| N | Analytics | reads only |

Modules H and I stay off unless the site shows the signal, so a site with no
hreflang never gets advice about hreflang.

Two things here are unusual enough to call out.

**Module E tests each AI crawler three ways**, because the three can disagree and
the disagreement is usually the finding. It evaluates robots.txt rules for the
crawler's token under RFC 9309 precedence, fetches pages sending that crawler's
user-agent string, and compares both against the policy you declared. It also
diffs the robots.txt served live against the one in your repository, which is how
a content delivery network quietly rewriting it gets caught. Anthropic and OpenAI
each run separate crawlers for training, search indexing and user-triggered
fetches, and blocking the training one does not block the others.

**The two scores are never combined.** Search health and AI access move
independently. A site can be technically excellent and invisible to assistants
because a firewall rule refuses them, or wide open to every crawler while its
canonical tags contradict its sitemap. Averaging those into one number destroys
the only information worth having. Both formulas are written out in
`reference/scoring.md` and printed next to the numbers, so a score can be argued
with.

## What it does with the findings

A list of defects is not a decision. Two things turn one into the other.

**Findings are ranked by the traffic they affect**, not by severity alone. Once
Search Console and Analytics are connected, a warning on a page earning 900
impressions outranks an error on a page nobody has ever reached. Severity still
matters, it multiplies rather than being replaced, so an error on a quiet page
still beats a notice on a busy one. Without those two connected, ordering falls
back to severity and the report says so, because a confident ranking built on no
data is worse than an honest unranked list.

**The report ends with a brief for whoever maintains the site.** siteseo does not
know your templating language, your voice, or why a page exists. The agent
working in that repository does. So the last section states, for each finding
worth acting on: what is wrong, the fix, how much traffic it touches, whether
it needs judgement, and the source backing the rule. It also lists what is
already working, the pages earning clicks and whether AI assistants send anyone,
because protecting those matters as much as fixing defects.

### Mechanical fixes and content are separated deliberately

`/siteseo fix` writes **mechanical SEO only**: structure, attributes and
configuration, where the correct value follows from a rule. robots.txt generated
from your policy, canonical tags, image dimensions, sitemap entries, hreflang
codes, redirect rules, schema properties, an IndexNow key.

It never writes **content**. A title, a description, alt text, a heading, a
rewrite. Those are words, and the right words depend on what the page is for and
how the site sounds. They go to the brief instead, for a human or the site's own
agent to decide. A tool that rewrites your titles because they are four
characters too long has misunderstood its job.

Even within mechanical, nothing is written until you pass `--apply`, and it
edits source rather than build output. Editing a build directory produces a file
the next build overwrites, which looks like a fix and is not one.

## What it does not check, and why

Every item here is a deliberate exclusion with a reason, not a gap.

**No traffic estimates for domains you do not own.** Every vendor number for
those is modeled from clickstream panels, not measured. Presenting a model as a
measurement is the single most misleading thing SEO tooling does.

**No full backlink index.** Building one is not feasible at this scale. Your own
links come free from the
[Search Console links report](https://support.google.com/webmasters/answer/9049606)
and Ahrefs free tier exports, imported as CSV. Only competitor links need a paid
call, and only when you ask.

**No toxic-link scores and no generated disavow files.** Google's
[own guidance](https://support.google.com/webmasters/answer/2648487)
is that most sites should never use the disavow tool. siteseo mentions disavow
only when Search Console reports a manual action.

**No single blended AI visibility score.** Assistant answers change between runs,
accounts and locations. siteseo reports a citation rate with its sample size and
the change since the last run. A rate without an n is not a measurement.

**No llms.txt scoring.** It is reported present or absent at notice level and
affects neither score. Google's
[generative AI guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)
says it is not needed, and the
[Ahrefs study](https://ahrefs.com/blog/llmstxt-study/) found no effect.

**No FAQPage or HowTo recommendations.** Google
[narrowed FAQ rich results to a small set of sites and dropped HowTo entirely in
2023](https://developers.google.com/search/blog/2023/08/howto-faq-changes).
Pages that already carry the markup get a notice saying so.

**No Google-specific AI markup or content chunking advice.** Google's generative
AI guide states that AI Overviews and AI Mode run on core Search ranking and
quality systems. There is nothing extra to add for them beyond ordinary SEO.

**No keyword density, LSI keywords, or similar folklore.**

**No PPC, social scheduling, or bulk content generation.**

**No automated content rewrites, page deletions, or noindex changes.** Those are
judgement calls. siteseo describes what it would change and stops.

One honest limit, which is a property of the method rather than a choice. A 200
response to a spoofed user-agent string proves only that robots rules and
user-agent filtering did not block that request. Some operators verify crawler IP
ranges, so the real crawler could still be refused. Only bot-hit logs confirm
actual access, which is why module K reads them. Wherever this check appears, the
report says so.

## Cost

Baseline is zero, and that is the default. Nothing in the list below runs without
a key you chose to add.

| What | Cost | Needs |
| --- | --- | --- |
| Crawl, on-page, structured data, AI crawler access, the gate | free | nothing |
| Search Console pulls, URL Inspection | free | a service account |
| Bing Webmaster data | free | an API key |
| PageSpeed Insights, CrUX field data | free | a PageSpeed key |
| AI visibility tracking | per call | model API keys |
| Keyword and SERP research, competitor backlinks | per request | a DataForSEO account |

The last two spend money, so they are capped. Set `budget.monthly_usd` in
`siteseo.yaml`. Every paid call prints its estimated cost and what remains of the
month before it runs, and refuses rather than exceeding the cap. Spend is
recorded in the site repository alongside everything else, so the running total
travels with the site. The cap defaults to zero, which means paid calls are off
until you turn them on.

## Configuration

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

# What you want AI crawlers to be able to do. siteseo flags any mismatch between
# this and what robots.txt and your CDN actually do, in both directions.
ai_policy:
  search_and_user_fetch: allow   # OAI-SearchBot, ChatGPT-User, Claude-SearchBot,
                                 # Claude-User, PerplexityBot, Perplexity-User
  training: allow                # GPTBot, ClaudeBot, Google-Extended,
                                 # Applebot-Extended, CCBot

# Questions a real customer would type. Used by `siteseo track`.
prompts:
  - "how do I keep AI crawlers from being blocked by my CDN"

competitors:
  - competitor-one.com

budget:
  monthly_usd: 0

secrets: env
```

Secrets never go in this file. It names them; the values live in your operating
system's vault or your environment. `doctor` reports which names resolve on the
current machine and never prints a value. A test asserts that no credential
pattern appears anywhere in the repository.

## Commands

| Command | What it does |
| --- | --- |
| `/siteseo audit [url]` | Full audit. Build output by default, a live URL when given. |
| `/siteseo page <url>` | Every module against one page. |
| `/siteseo ai` | Module E only. Prints the crawler matrix. |
| `/siteseo pull` | Search Console and Bing into dated history. |
| `/siteseo track` | Run the AI visibility prompt set. |
| `/siteseo research <term>` | Paid keyword research, after a cost estimate. |
| `/siteseo fix [ids]` | Propose diffs for autofixable findings. |
| `/siteseo report` | Latest snapshot and the diff against the previous one. |
| `/siteseo indexnow` | Push changed URLs to Bing, Yandex, Seznam and Naver. |
| `/siteseo gate` | Pre-deploy gate. No model calls, no paid APIs. |
| `/siteseo setup` | Build or refresh the isolated Python environment. |
| `/siteseo doctor` | Runtime, secrets and reference staleness on this machine. |
| `/siteseo sync` | Check upstream and reference drift. |

Every script also runs standalone, without Claude, which is what makes the gate
usable in continuous integration:

```
"${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run gate.py
```

## Fix mode

`fix` prints diffs and writes nothing until you pass `--apply`. It edits source
templates and configuration, never built HTML, because editing `dist/` produces a
file the next build silently overwrites. That looks like a fix and is not one.

Where it cannot locate the source with confidence, it says what to change and
stops rather than guessing at a templating language it cannot verify. A tool that
half-understands your Astro components will produce a broken build, not a fixed
page.

## The gate

```
/siteseo gate
```

Modules A, B, C and E against build output. Exits 1 on any error. Warnings and
notices never block. On a small site it finishes in under a second.

It makes no model call and no paid API call, and that is enforced rather than
promised. The run sets an offline flag, and the network source refuses to be
constructed while that flag is set. `tests/test_gate_offline.py` asserts the
refusal actually fires and that the gate still produces a complete result with
the network unavailable.

As a pre-push hook:

```bash
# .git/hooks/pre-push
npm run build && "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run gate.py || exit 1
```

In GitHub Actions:

```yaml
- run: npm run build
- run: "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run gate.py
```

## Where your data lives

Everything a site needs travels with the site repository and is committed.

```
<site repo>/
  siteseo.yaml
  .siteseo/history/    dated JSON snapshots
  .siteseo/reports/    dated markdown reports
  .siteseo/imports/    manual CSV exports
```

This is the point. Clone the repository on another machine and the trend is
already there. Nothing depends on a cache directory that exists in one home
folder on one laptop, which is how most tooling quietly loses your history.

Drop CSV exports into `.siteseo/imports/` for the data that has no API:
`bing-ai/` for Bing AI Performance exports, `backlinks/` for Search Console or
Ahrefs link exports, `logs/` for access logs from your host or CDN. Those Bing
grounding queries are worth the effort: they are real questions that already
retrieved your pages, which makes them the best seed for the AI visibility
prompt set.

## Staying current

Two clocks drift independently and both are tracked.

Vendored code is pinned in `upstream.lock` by commit and content hash. The
reference data carries `last_verified` dates, because crawler names and rich
result rules change without any repository moving. A weekly job checks both and
opens one pull request showing exactly what moved and what has passed ninety
days. Nothing executes on any machine until you read that diff and merge it.

`/siteseo doctor` warns locally when a pin is behind or a reference file has gone
stale. Continuous integration also re-checks every source URL in the check
catalog on a schedule, because documentation sites reorganise. Google moved its
crawling documentation to a new path during this project's first day, which is
exactly why that check exists.

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

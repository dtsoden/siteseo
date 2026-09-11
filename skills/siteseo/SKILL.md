---
name: siteseo
description: "Search and AI search readiness auditing for sites you own. Audits a local build directory or a live URL, reports findings with raw evidence and a source link for each, keeps search health and AI access as two separate scores, pulls first-party Search Console and Bing data into dated history committed to the site repo, tracks whether AI assistants cite you, applies safe fixes to source templates behind a diff, and gates deploys with no model calls and no paid API calls. Triggers on: SEO, SEO audit, technical SEO, robots.txt, sitemap, canonical, structured data, schema markup, Core Web Vitals, AI crawlers, GPTBot, ClaudeBot, AI search, AI visibility, Search Console, deploy gate, pre-push SEO check."
user-invocable: true
argument-hint: "[command] [url]"
license: MIT
metadata:
  author: dtsoden
  version: "0.1.2"
  category: seo
---

# siteseo

**Invocation:** `/siteseo $1 $2` where `$1` is the command and `$2` is an optional
URL or argument.

**Runtime:** run every bundled tool through
`"${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run <script.py>`. That is the only
supported form. Never call a bundled script with a bare interpreter: it will not
see the pinned dependencies. If a run reports that setup is required, tell the
user to run `/siteseo setup` and stop. Do not improvise a `pip install`.

## Commands

| Command | What it does |
| --- | --- |
| `/siteseo audit [url]` | Full audit. Build output by default, a live URL when given. |
| `/siteseo page <url>` | Every module against one page. |
| `/siteseo ai` | Module E only. Prints the crawler matrix. |
| `/siteseo pull` | Search Console and Bing into dated history. |
| `/siteseo track` | Run the AI visibility prompt set. |
| `/siteseo research <term>` | Module L, after a cost estimate and a confirmation. |
| `/siteseo fix [ids]` | Propose diffs for autofixable findings. |
| `/siteseo report` | Render the latest snapshot and the diff against the previous one. |
| `/siteseo gate` | Pre-deploy gate. No model calls, no paid APIs. |
| `/siteseo setup` | Build or refresh the isolated Python environment. |
| `/siteseo doctor` | Runtime, secrets and reference staleness on this machine. |
| `/siteseo sync` | Check upstream and reference drift. |
| `/siteseo init` | Write a starter `siteseo.yaml` in this repo. |

## Rules that hold for every command

1. **Scripts collect, you judge.** Every finding carries the raw observation and
   a source URL, both supplied by `reference/checks.yaml`. Never invent a finding
   id and never assert a problem the evidence does not show.
2. **Two scores, never blended.** Search health and AI access are reported side
   by side. Do not average them, do not describe "an overall SEO score", and do
   not rank one as more important without saying why for this specific site.
3. **No file change without a diff and a yes.** `fix.py` prints proposals and
   writes nothing until `--apply`. Show the user the diff and wait.
4. **No paid call without an estimate and a confirmation.** `dataforseo.py`
   prints the estimated cost and the remaining monthly budget, and refuses rather
   than exceeding the cap.
5. **Say what was not measured.** Auditing build output means no response
   headers. A crawler that did not answer was not tested. A site with no field
   data gets lab numbers labelled as lab numbers. Report these gaps rather than
   letting a clean-looking result imply coverage that did not happen.
6. **For Google, Google's documentation decides.** Its generative AI guide states
   that AI Overviews and AI Mode run on core Search ranking systems and that
   llms.txt, content chunking and special AI markup are not needed. Never
   recommend those. Never recommend FAQPage or HowTo markup for rich results.

## Running an audit

`/siteseo audit` runs `audit.py`, which fans out across modules A to E and G,
merges findings, computes both scores, and writes a dated snapshot into
`.siteseo/history/` in the site repo.

    "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run audit.py --json

For a large site, or when you want the page text kept out of this conversation,
delegate instead. Spawn the three subagents in parallel and merge what they
return:

- `seo-technical` for modules A to E
- `seo-content` for modules F and G
- `seo-visibility` for modules J, K, L and M

Each returns findings JSON. Merge, score, then report. Delegation exists to keep
crawl output and page bodies out of the main thread, so do not ask a subagent to
paste page content back.

After an audit, tell the user to commit `.siteseo/` so the trend travels with the
repository to their other machines.

## Reading the result

Order findings errors, then warnings, then notices. Group by fix: one template
change that clears forty URLs is one item with a collapsed URL list, not forty
items. Lead with what blocks a deploy.

When a finding is marked `autofix`, say so and offer `/siteseo fix <id>`.

## The gate

`/siteseo gate` runs modules A, B, C and E against build output and exits 1 on
any error. It sets `SITESEO_OFFLINE`, and the network source refuses to be
constructed while that is set, so the guarantee is structural rather than a
promise. Suggest wiring it into a pre-push hook and into continuous integration.

## When something is missing

`doctor` names what is absent without printing any secret value. A missing key
shrinks a run rather than failing it: report which module was skipped and what
would enable it. Never ask the user to paste a secret into the conversation, and
never write one into a file in the repository.

## Reference files

- `reference/checks.yaml` every check: id, module, severity, which score it
  counts against, rule, source URL, fix, autofix flag.
- `reference/ai-bots.yaml` crawlers, their operators, what each is for, and the
  operator documentation that says so.
- `reference/rich-results.yaml` required and recommended properties per
  structured data type.
- `reference/scoring.md` both formulas, written out.
- `reference/perf-guidance.md` Core Web Vitals guidance, vendored from
  addyosmani/web-quality-skills.

Each carries a `last_verified` date. `doctor` and `sync` warn when one passes
ninety days, because crawler names and rich result rules change without any
repository moving.

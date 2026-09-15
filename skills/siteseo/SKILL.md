---
name: siteseo
description: "EXPLICIT INVOCATION ONLY. Use this skill only when the user types the /siteseo command, or names siteseo directly and asks to run it. Never invoke it because a task mentions SEO, sitemaps, robots.txt, canonicals, structured data, Core Web Vitals or AI crawlers, and never invoke it as a step inside another job such as publishing, deploying or writing a page. An audit crawls a whole site and costs time and tokens, so it runs when asked for and at no other time. What it does when asked: search and AI search readiness auditing for sites the user owns, against a local build directory or a live URL."
user-invocable: true
argument-hint: "[command] [url]"
license: MIT
metadata:
  author: dtsoden
  version: "0.5.0"
  category: seo
---

# siteseo

## Run only when asked

This skill is explicit-invocation only. Use it when the user types `/siteseo`, or
names siteseo and asks for it. Do not reach for it because a task happens to
involve SEO, and do not run it as a step inside publishing or deploying unless
the user's own instructions for that job say to.

An audit crawls an entire site. In an unattended session that is someone's token
budget and someone's deploy pipeline, so the cost of guessing wrong is real.

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
| `/siteseo` | Guided start. Checks where this repo stands and walks the user through setup, config and a first full report. |
| `/siteseo status` | Where this repo stands: environment, config, last report, next step. |
| `/siteseo audit [url]` | Full audit. Build output by default, a live URL when given. |
| `/siteseo page <url>` | Every module against one page. |
| `/siteseo ai` | Module E only. Prints the crawler matrix. |
| `/siteseo agents [--live] [--compare-cloudflare]` | Module O only. Agent readiness level and checks. |
| `/siteseo markdown [--setup] [--llms-txt]` | Write a .md file next to every built page, and the host rule that serves it. |
| `/siteseo pull` | Search Console and Bing into dated history. |
| `/siteseo track` | Run the AI visibility prompt set. |
| `/siteseo research <term>` | Module L, after a cost estimate and a confirmation. |
| `/siteseo fix [ids]` | Propose diffs for autofixable findings. |
| `/siteseo report` | Render the latest snapshot and the diff against the previous one. |
| `/siteseo indexnow` | Push changed URLs to Bing, Yandex and others. |
| `/siteseo gate` | Pre-deploy gate. No model calls, no paid APIs. |
| `/siteseo setup` | Build or refresh the isolated Python environment. |
| `/siteseo doctor` | Runtime, secrets and reference staleness on this machine. |
| `/siteseo sync` | Check upstream and reference drift. |
| `/siteseo init` | Write a starter `siteseo.yaml` in this repo. |

## No command: the guided start

A bare `/siteseo` means the user wants to be walked through it. Most people will
not remember the commands, and they should not have to. Start by finding out
where the repository stands:

    "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" status --json

`status` runs before setup has ever happened and makes no network request. Act on
`next_step`, one step at a time, asking before each one. Keep every explanation to
a sentence or two. Offer choices rather than open questions wherever the answer
is one of a few, and put what `detected` found first, marked as recommended.

1. **`setup`.** The Python environment is not built on this machine. Say it is a
   one-time step of about a minute that installs into its own folder and touches
   nothing else. On a yes, run `siteseo setup`, then run `status` again.
2. **`init`.** There is no siteseo.yaml. Ask for:
   - the live site address, typed by the user;
   - the build output folder, offering `detected.build_dirs`, plus "no build
     step, audit the live site only";
   - the host, offering `detected.host` first;
   - what AI systems may do: "search and answers, but no training" (search allow,
     training block), "everything" (both allow), or "nothing" (both block);
   - what the site is, for agent readiness: pages people read (`content`), a
     public API (`api`), or selling to agents (`commerce`).

   Write the file from the repository root with the answers:

       "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run config.py --init --site <url> --build-dir <dir> --host <host> --search <allow|block> --training <allow|block> --profile <profile>

   Leave out `--build-dir` for a live-only site. Show the user the file, then run
   `status` again.
3. **`build`.** siteseo.yaml names a build folder that does not exist yet. Offer
   to run the site's build (look for the build script in package.json or the
   stack's usual command), or to run the report against the live site instead.
4. **`first_report`.** Configured, never audited. Ask whether to run the first
   full report now. Say what it covers: every page, technical SEO, on-page,
   structured data, AI crawler access and agent readiness, at no cost, in a few
   minutes. Ask whether to check the live site, the build output, or both, and
   recommend the live site when it is deployed, because only a live check sees
   response headers and what crawlers actually get back. Then follow
   "The full report" below.
5. **`ready`.** A report exists. Give the date and the headline numbers from
   `latest_audit` in one line, then offer: run a fresh full report, work through
   the last report, apply the mechanical fixes, set up Markdown for agents, or
   something else.

## The full report

A full report is `audit.py`, live or against build output:

    "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run audit.py --live
    "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run audit.py

It writes `.siteseo/reports/<date>-audit.md`, which covers what is there as well
as what is not: both scores, the agent readiness level with every check, a table
of every module saying what it found or why it did not run, the crawler matrix,
the findings, and a brief ranked for whoever maintains the site. Read that file
rather than the terminal output, and summarise it in this order:

1. Search health and AI access, with one line each on what drives them.
2. The agent readiness level and the single next step up.
3. What blocks a deploy, if anything.
4. The five findings the brief ranks highest, each in a sentence.
5. Modules that did not run and what would switch each one on, such as a
   PageSpeed key for performance or Search Console for query data.

Then ask what to work on. When the user picks something, take it one finding at
a time: say what is wrong and what the fix is, propose the change, and wait for a
yes. Mechanical findings go through `/siteseo fix`. Content findings are drafted
as an edit to the source for the user to approve, never applied on your own.
After a batch of fixes, offer to re-run the report so the snapshot diff shows
what moved, and remind the user to commit `.siteseo/`.

## Rules that hold for every command

1. **Scripts collect, you judge.** Every finding carries the raw observation and
   a source URL, both supplied by `reference/checks.yaml`. Never invent a finding
   id and never assert a problem the evidence does not show.
2. **Two scores, never blended.** Search health and AI access are reported side
   by side. Do not average them, do not describe "an overall SEO score", and do
   not rank one as more important without saying why for this specific site.
   The agent readiness level from module O sits beside them as a level, never as
   a third score and never averaged in.
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
   recommend those for Google. `/siteseo markdown --llms-txt` exists for agents
   other than Google Search; offer it only when the user asks about an index of
   Markdown pages. Never recommend FAQPage or HowTo markup for rich results.
   Module O does check Markdown negotiation, Content Signals and other agent
   standards, because assistants and agents other than Google Search use them.
   Whenever you report module O, say it has no effect on Google Search.

## Running an audit

`/siteseo audit` runs `audit.py`, which fans out across modules A to E, G, H, I and O,
merges findings, computes both scores and the agent readiness level, and writes a
dated snapshot into `.siteseo/history/` in the site repo.

    "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run audit.py --json

For a large site, or when you want the page text kept out of this conversation,
delegate instead. Spawn the three subagents in parallel and merge what they
return:

- `seo-technical` for modules A to E and O
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

## Agent readiness

`/siteseo agents` runs module O.

    "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run agent_ready.py                 build output
    "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run agent_ready.py --live          the deployed site
    "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run agent_ready.py --live --compare-cloudflare

It places the site on the 0 to 5 ladder that Cloudflare's Agent Readiness
scanner publishes (isitagentready.com, and the Agent Readiness tab in the
Cloudflare dashboard) and lists every check with its status. When the result
carries a ceiling, say the level could be higher and name what was not
measured. Do not round it up. Build output has no response headers, so Link
headers and Markdown negotiation need `--live`.

`agent_readiness.profile` in siteseo.yaml decides which absences become
findings: `content` by default, `api`, or `commerce`. A content site is never
told to build an OAuth server, and a skipped row is not a pass. If the site does
run an API or sell to agents, suggest changing the profile.

When reporting module O, be plain about these:

- It has no effect on Google Search.
- Nothing in it requires Cloudflare. Every check is a public RFC, draft or vendor
  spec. Mention Cloudflare's shortcuts, such as Markdown for Agents or managed
  robots.txt, when `host` is `cloudflare-pages` or the user asks.
- Where siteseo and the scanner disagree, siteseo follows the current spec.
  `reference/agent-readiness.md` lists each place and why.
- Commerce checks are informational and outside the level, as they are in
  Cloudflare's dashboard.

`--compare-cloudflare` sends the site's URL to isitagentready.com and lists
every check where the two answers differ. Run it only when the user asks for
the comparison. It refuses to run while `SITESEO_OFFLINE` is set, and the gate
never calls it.

The one mechanical fix is the Content-Signal line, which `/siteseo fix` derives
from `ai_policy` and writes without touching the other robots.txt rules. Read
the values out before offering it: `ai-input=no` asks assistants not to use the
site in answers, which works against being cited.

## Markdown for agents

`/siteseo markdown` gives agents a Markdown copy of every page without paying for
Cloudflare's Markdown for Agents. It is two steps.

**Export, on every build.** It reads the built HTML, keeps the main content, and
writes a `.md` next to each page (`about/index.html` becomes `about/index.md`),
with frontmatter naming the title, description and canonical URL. It adds a
`<link rel="alternate" type="text/markdown">` tag to each page, skips noindex and
error pages, never touches a `.md` file it did not write, and removes the ones it
wrote whose page is gone.

    "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run markdown_export.py

It works on build output, so it has to run after every build. Offer to add it to
the site's build script after the build command. Running it once and committing
the output leaves it stale after the next content change.

**Serve, once.** Static files cannot look at an `Accept` header, so the host
needs one rule that picks the `.md` for an agent. `--setup` generates it for the
`host` in siteseo.yaml, or the one passed with `--serve`:
`cloudflare-pages`, `cloudflare-worker`, `netlify`, `vercel` or `nginx`. It prints
the files and writes nothing until `--apply`, and never overwrites an existing
file.

    "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run markdown_export.py --setup
    "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run markdown_export.py --setup --serve cloudflare-worker --apply

Pick the serving rule by where requests pass as well as where files live. A site
hosted anywhere whose DNS is proxied through Cloudflare can use
`cloudflare-worker`, on the free plan. GitHub Pages cannot negotiate at all; say
so and offer the Worker if the domain is on Cloudflare. After deploying, run
`/siteseo agents --live` to confirm agents get Markdown. The Vercel handler is
the least proven of the five, so tell the user to try it on a preview first.

`--llms-txt` also writes an `llms.txt` listing every exported page. There is no
RFC for an index of Markdown pages. llms.txt is the community convention some
agents look for. Google ignores it, and Cloudflare's scanner no longer checks it. Offer it when the user asks for an index; do not push it.

## Telling search engines about a change

`/siteseo indexnow` submits URLs to IndexNow, which reaches Bing, Yandex, Seznam
and Naver through one free endpoint and needs no account.

    "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run indexnow.py --setup     once per site
    "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run indexnow.py --changed   after a deploy
    "${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run indexnow.py             whole sitemap

Setup writes a key file into the site's source, never into build output, since
build output is regenerated and the key would vanish. Deploy before submitting:
IndexNow fetches the key file itself to prove you control the domain, and the
script refuses to submit until it can see it live.

**Google does not participate in IndexNow.** Its Indexing API accepts only
JobPosting and BroadcastEvent pages, so an ordinary page cannot be submitted to
Google programmatically at all. That is Request indexing in Search Console, by
hand, roughly ten a day. Say so rather than implying IndexNow covers Google.

Prefer `--changed` in a deploy hook. Submitting forty unchanged pages on every
deploy is noise, and a noisy submitter gets ignored.

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
- `reference/agent-readiness.md` every agent standard module O checks with its
  current status, and each place siteseo and the scanner differ.
- `reference/agent-readiness.yaml` the scanner-to-check mapping and the pinned
  digests of the scanner's published skills, which `sync` watches.
- `templates/markdown/` the per-host handlers `/siteseo markdown --setup` writes.
- `reference/perf-guidance.md` Core Web Vitals guidance, vendored from
  addyosmani/web-quality-skills.

Each carries a `last_verified` date. `doctor` and `sync` warn when one passes
ninety days, because crawler names and rich result rules change without any
repository moving.

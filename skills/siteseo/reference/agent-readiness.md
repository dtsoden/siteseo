# Agent readiness

last_verified: 2026-09-15

Module O checks whether AI agents, rather than search engines, can find, read,
authenticate to and transact with a site. It reports a level on the same 0 to 5
ladder Cloudflare's scanner uses, lists every check with its evidence, and never
touches the search health or AI access scores.

None of this moves Google rankings. Google's
[AI optimization guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)
says "You don't need to create new machine readable files, AI text files,
markup, or Markdown to appear in Google Search (including its generative AI
capabilities), as Google Search itself doesn't use them." Module O is for
everyone else: assistants fetching a page for a user, agents calling an API,
browsers exposing site actions as tools, and payment flows run by software.

## Where this comes from

Cloudflare launched the public scanner at [isitagentready.com](https://isitagentready.com)
on 2026-04-17 ([announcement](https://blog.cloudflare.com/agent-readiness/)).
On 2026-08-06 it moved the same checks into the dashboard as an Agent Readiness
tab with a Diagnostics view that groups them as quick wins, technical
groundwork, advanced integration and commerce, each failed item carrying either
a Set up in Cloudflare link or a Copy Agent Prompt button
([announcement](https://blog.cloudflare.com/aeo/)). The checks also appear in
URL Scanner (2026-05-12) and in Radar.

Status as of the date above. Neither announcement calls Agent Readiness a beta,
and the developer documentation has no page for the dashboard tab yet. The
early-access wording in the August post is about AEO Visibility, a separate
feature. Plan availability for the tab is not published. Treat the dashboard as
early and expect it to change.

The scanner's source is not public. The criteria siteseo uses come from the
specs themselves, from the scanner's published skill files at
`/.well-known/agent-skills/`, and from the evidence trail its API returns.

## Is any of it specific to Cloudflare

No check requires Cloudflare. Every one is a public RFC, draft or vendor spec
that any host can serve. Cloudflare offers shortcuts for some of them, and a few
of the specs are ones Cloudflare wrote or leads.

| Check | Any host | Cloudflare shortcut |
| --- | --- | --- |
| robots.txt, AI rules, Content Signals | edit robots.txt | managed robots.txt in Security Settings, all plans |
| Markdown negotiation | an edge function, or pre-built .md files behind Accept negotiation | Markdown for Agents, Pro plan and above |
| Link headers | a `_headers` file on Netlify or Pages, or server config | Transform Rules or a Worker |
| OAuth metadata | your authorization server | Cloudflare Access as the identity provider |
| MCP and A2A cards | any static JSON | Agents SDK on Workers |

Cloudflare's managed robots.txt writes a `Content-signal: search=yes, ai-train=no`
line and Disallow groups for eight training crawlers in front of your own file.
siteseo's module E already compares the served robots.txt with the repository
copy and will report that difference as `ai.robots_live_differs_from_repo`.
That is expected when managed robots.txt is on; confirm it matches ai_policy
rather than treating it as a fault. Cloudflare also notes Search Console may
show "Syntax not understood" for Content-Signal lines, with no crawl impact.

## The ladder

| Level | Name | Needs |
| --- | --- | --- |
| 0 | Not Ready | fewer than two of robots.txt, sitemap, Link headers |
| 1 | Basic Web Presence | two of robots.txt, sitemap, Link headers |
| 2 | Bot-Aware | level 1, AI crawler rules and Content Signals |
| 3 | Agent-Readable | level 2 and Markdown negotiation |
| 4 | Agent-Integrated | level 3 and one of MCP card, A2A card, skills index, API catalog |
| 5 | Agent-Native | level 4 and two of: Web Bot Auth, all four level 4 documents, auth metadata (OAuth discovery, protected resource metadata or auth.md) |

Commerce checks sit outside the ladder, as they do in Cloudflare's dashboard.

Two places siteseo reads the ladder more strictly. First, a check that could not
be measured does not count as passing. Build output has no response headers, so
Link headers and Markdown negotiation are unmeasured there and the level is
reported as a ceiling with the reason. Cloudflare's scanner treats a check left
out of a scan as satisfied, which can report level 5 for a site that fails
robots.txt. Second, the phrase "all integrations" in the level 5 rule is read as
all four level 4 documents. The published text does not define it, and scans of
level 4 sites asking for exactly the missing card and auth metadata fit this
reading.

## Profiles

A music site does not need an OAuth server. `agent_readiness.profile` in
siteseo.yaml decides which absences are reported.

- `content`, the default. Levels 1 to 3 are reported as findings. The level 4
  documents and Web Bot Auth are still fetched, so a real level 4 is recognised,
  but their absence is not reported.
- `api`. Adds the level 4 and 5 documents, WebMCP, DNS-AID and ARD.
- `commerce`. Adds ACP, UCP, MPP, x402 and AP2, reported for information.

A document that is published and broken is reported whatever the profile.

## Every standard, and where it stands

| Standard | Where | Status on 2026-09-15 | Origin |
| --- | --- | --- | --- |
| robots.txt | `/robots.txt` | [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html), Proposed Standard | open standard |
| Sitemap | `/sitemap.xml` | [sitemaps.org 0.9](https://www.sitemaps.org/protocol.html) | open standard |
| Link headers | `Link` response header | [RFC 8288](https://www.rfc-editor.org/rfc/rfc8288.html), relation from [RFC 9727](https://www.rfc-editor.org/rfc/rfc9727.html) | open standard |
| Content Signals | `Content-Signal:` in robots.txt | [contentsignals.org](https://contentsignals.org/); its IETF draft expired 2026-04-04 | Cloudflare-led |
| IETF AI preferences | `Content-Usage:` in robots.txt or a header | [draft-ietf-aipref-vocab-08](https://datatracker.ietf.org/doc/draft-ietf-aipref-vocab/) and attach-05, no consensus yet | IETF working group |
| Markdown negotiation | `Accept: text/markdown` | no spec; [Cloudflare's implementation](https://developers.cloudflare.com/fundamentals/reference/markdown-for-agents/) is the reference | Cloudflare-led |
| API catalog | `/.well-known/api-catalog` | [RFC 9727](https://www.rfc-editor.org/rfc/rfc9727.html), Standards Track | open standard |
| OAuth discovery | `/.well-known/oauth-authorization-server`, `/.well-known/openid-configuration` | [RFC 8414](https://www.rfc-editor.org/rfc/rfc8414.html), OIDC Discovery 1.0 | open standard |
| Protected resource metadata | `/.well-known/oauth-protected-resource` | [RFC 9728](https://www.rfc-editor.org/rfc/rfc9728.html) | open standard |
| auth.md | `/auth.md` plus `agent_auth` in server metadata | [WorkOS auth.md](https://github.com/workos/auth.md) 0.6.0 | vendor |
| MCP server card | `/.well-known/mcp/server-card.json` today | SEP-1649 closed, [SEP-2127](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2127) open and unmerged | MCP community |
| A2A Agent Card | `/.well-known/agent-card.json` | [A2A 1.0.1](https://a2a-protocol.org/latest/specification/) | Linux Foundation project |
| Agent skills index | `/.well-known/agent-skills/index.json` | [discovery RFC 0.2.0](https://github.com/cloudflare/agent-skills-discovery-rfc), draft | Cloudflare-led |
| Web Bot Auth | `/.well-known/http-message-signatures-directory` | [draft-ietf-webbotauth-httpsig-protocol-00](https://datatracker.ietf.org/doc/draft-ietf-webbotauth-httpsig-protocol/) | IETF working group, Cloudflare and Google authors |
| WebMCP | `document.modelContext.registerTool` | [W3C community group draft](https://webmachinelearning.github.io/webmcp/), Chrome 149 origin trial | community |
| DNS-AID | SVCB at `_index._agents.<host>` | [individual draft -02](https://datatracker.ietf.org/doc/draft-mozleywilliams-dnsop-dnsaid/) | community |
| ARD | `/.well-known/ard.json` | [proposal 0.91](https://agenticresourcediscovery.org/spec/) | community |
| ACP | `/.well-known/acp.json` | [OpenAI and Stripe](https://github.com/agentic-commerce-protocol/agentic-commerce-protocol), beta; discovery is an RFC proposal | vendor |
| UCP | `/.well-known/ucp` | [ucp.dev](https://ucp.dev/latest/specification/overview/) | vendor |
| MPP | `x-payment-info` in `/openapi.json` | [mpp.dev](https://mpp.dev/advanced/discovery), IETF individual draft | vendor |
| x402 | HTTP 402 with `PAYMENT-REQUIRED` | [x402 v2](https://github.com/x402-foundation/x402) | vendor, Cloudflare co-founded the foundation |
| AP2 | extension on the A2A Agent Card | [AP2 0.2.0](https://github.com/google-agentic-commerce/AP2) | vendor |

llms.txt is not on the ladder. Cloudflare's scanner dropped it as a check, and
module E already reports it for information only.

## Where siteseo and the scanner disagree

Each of these is a place where the scanner, or the agent prompts it hands out,
lags the current spec. siteseo follows the spec and says so in the finding.

- AI crawler rules. The scanner passes a robots.txt with only a wildcard group,
  while its own skill file says a wildcard alone is not enough. siteseo passes
  the wildcard for the level, because module E already tests every current
  crawler against it. The scanner's bot list also includes `anthropic-ai` and
  `Claude-Web`, which Anthropic no longer documents, and omits `ClaudeBot`.
  siteseo reports groups that name only obsolete tokens.
- MCP server card. The scanner reads `/.well-known/mcp/server-card.json`, the
  path from SEP-1649. That proposal was closed and replaced by SEP-2127, whose
  discovery document rejects a well-known card path and lists cards from a
  catalog instead. SEP-2127 is not merged, so siteseo accepts the legacy path
  and recommends serving both.
- WebMCP. The scanner's prompt says `navigator.modelContext`. The API moved to
  `document.modelContext` in May 2026. siteseo cannot run a browser, so it looks
  for either call in the page and its same-origin scripts and says the result is
  a static read.
- A2A. The scanner's prompt matches 1.0. Cards written against 0.3 still carry
  top-level `url` and `preferredTransport`, which 1.0 removed; siteseo flags
  them as legacy.
- auth.md. The scanner's prompt names `register_uri`, `claim_uri` and
  `verified_email`. auth.md 0.6.0 replaced those.
- ARD. The scanner looks for `/.well-known/ai-catalog.json`. The spec renamed it
  to `ard.json`; siteseo reads both.
- Levels on partial scans, described above.

Run `/siteseo agents --compare-cloudflare` to see the two answers side by side
for a live site.

## Content Signals and ai_policy

The Content-Signal line siteseo writes comes from ai_policy, unless
`agent_readiness.content_signals` overrides it.

| Signal | Means | Default source |
| --- | --- | --- |
| `search` | building a search index and showing links and excerpts | `search_and_user_fetch` |
| `ai-input` | using content as live input to an AI answer | `search_and_user_fetch` |
| `ai-train` | training or fine-tuning a model | `training` |

A common choice is `search=yes, ai-input=yes, ai-train=no`. Cloudflare's own
example prompt uses `ai-input=no`, which asks assistants not to quote the site
in answers. That is a legitimate choice, but it cuts against being cited, so
siteseo never picks it for you.

Signals are preferences. Nothing enforces them, and a crawler that ignores
robots.txt will ignore them too. The IETF AI preferences drafts use different
names (`Content-Usage`, `train-ai`, `ai-use`, `y` and `n`); siteseo reports a
`Content-Usage` line when it sees one but does not write it until those drafts
reach consensus.

## Keeping this current

This file carries a `last_verified` date and `doctor` flags it after ninety
days. `agent-readiness.yaml` pins the digest of every skill the scanner
publishes, and `/siteseo sync` fetches the scanner's index and reports any skill
added, removed or rewritten. A changed skill is usually the first public sign
that a check changed.

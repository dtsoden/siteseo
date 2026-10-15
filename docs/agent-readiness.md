[Docs home](README.md) / Agent readiness

# Agent readiness

Search engines are one kind of visitor. Agents are another: an assistant
fetching a page for someone, software calling your API, a browser exposing a
site's actions as tools, a payment made without a person at the keyboard.
Cloudflare launched a public scanner for this at
[isitagentready.com](https://isitagentready.com) in April 2026 and put it in the
dashboard as Agent Readiness in August. Module O runs the same checks against
your build output or your live site and places it on the same ladder, so you
can hold the two answers side by side.

| Level | Name | Needs |
| --- | --- | --- |
| 0 | Not Ready | fewer than two of robots.txt, sitemap, Link headers |
| 1 | Basic Web Presence | two of robots.txt, sitemap, Link headers |
| 2 | Bot-Aware | AI crawler rules and a Content-Signal line |
| 3 | Agent-Readable | Markdown served for `Accept: text/markdown` |
| 4 | Agent-Integrated | one of an MCP server card, A2A Agent Card, skills index, API catalog |
| 5 | Agent-Native | two of Web Bot Auth, all four of those documents, OAuth or auth.md metadata |

Commerce protocols (ACP, UCP, MPP, x402, AP2) are reported for information and
sit outside the ladder, as they do in Cloudflare's dashboard.

None of it requires Cloudflare. Every check is a public RFC, draft or vendor
spec that any host can serve; Cloudflare offers shortcuts for some, such as
Markdown for Agents on its Pro plan. None of it moves Google rankings either.
Google's
[AI optimization guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)
says Search ignores Markdown, AI text files and special markup, so module O is
about every other agent.

It departs from the scanner in a few places, on purpose:

- A check that could not be measured is not a pass. Build output has no response
  headers, so the level is reported as a ceiling with the reason rather than
  rounded up. The scanner treats a check left out of a scan as satisfied.
- `agent_readiness.profile` decides what counts as missing. `content` asks for
  robots.txt, Content Signals and Markdown. `api` adds the discovery and auth
  documents. `commerce` adds the payment protocols.
- Checks follow the current spec where the scanner lags it. The MCP server card
  proposal it reads has been replaced, WebMCP moved from `navigator` to
  `document`, and its crawler list still names tokens Anthropic retired.
  [agent-readiness.md](../skills/siteseoai/reference/agent-readiness.md) lists every
  standard, its status on the date it was checked, and each disagreement.

`/siteseoai agents --live --compare-cloudflare` also runs Cloudflare's scanner and
lists every check where the two answers differ, with the reason where it is
known. That sends your URL to Cloudflare, so it runs only when you ask for it.

The one fix siteseoai will write here is the Content-Signal line in robots.txt,
derived from `ai_policy` and inserted without touching your other rules.

---

Previous: [What it checks](checks.md) | Next: [What it does not check](not-checked.md)

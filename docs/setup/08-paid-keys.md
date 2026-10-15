[Docs home](../README.md) / [Setup guide](README.md) / Paid keys

# Paid keys

Checked against official documentation on 2026-10-14.

Everything on the earlier pages is free. The keys on this page spend money on
your own accounts with each provider, so set them up only when you want what
they add.

## Run siteseoai on a Claude subscription

The recommended way to run siteseoai is inside Claude Code on a Claude
subscription. The audit, the report, the brief and the fixes are all Claude Code
work, so they come out of the subscription you already pay for. The cost is the
subscription and nothing else, and when you reach your plan's limit, work stops
rather than running up a bill.

Anything that goes through an API key is metered instead, and the cost of a
task is hard to predict before you run it. Token counts vary from run to run,
because the model reads different pages, follows different links and writes
different amounts each time. One run tells you very little. If you do use API
keys, run the same task end to end several times, check the spend on each run,
and use the median as your cost per task before you budget around it.

The AI visibility keys below are the one place siteseoai needs an API at all,
because measuring citations means asking each assistant directly with web search
switched on. They are optional, and siteseoai runs fully without them. Prices quoted here are what each provider published on the date
above; their pricing pages are the authority.

## AI visibility tracking

Module K asks AI assistants the questions under `prompts:` in your
`siteseoai.yaml`, plus any grounding queries imported from
[Bing](07-bing.md#the-ai-performance-report), with web search switched on, and
records whether the answers cite your site. Each prompt runs three times per
provider, because answers vary between runs, and every rate is reported with
its sample size.

Each provider is independent. Set one, two or all three.

| Variable | Provider | Where the key comes from |
| --- | --- | --- |
| `SITESEOAI_ANTHROPIC_API_KEY` | Claude, with web search | [Claude Console](https://platform.claude.com/settings/keys) |
| `SITESEOAI_OPENAI_API_KEY` | OpenAI, with web search | [OpenAI Platform](https://platform.openai.com/settings/organization/api-keys) |
| `SITESEOAI_PERPLEXITY_API_KEY` | Perplexity Sonar | [Perplexity API console](https://console.perplexity.ai) |

All three are prepaid. A key works only after you have bought credits, and calls
stop when the credits run out.

### Anthropic

Sign in at platform.claude.com (console.anthropic.com now redirects there). Go
to **Settings**, then **API keys**, and click **Create key**. Copy it at once,
because it is shown only once. Buy credits under **Settings**, then **Billing**.
Web search costs $10 per 1,000 searches on top of normal token prices, and
failed searches are not billed.

### OpenAI

Create a key on the API keys page linked above and copy it when shown, since
OpenAI also shows it only once. Add credits under billing. siteseoai uses
`gpt-6-luna`, the lowest-cost model in OpenAI's newest family, GPT-6, at $0.10
per million tokens in and $0.50 out. The web search tool adds $10 per 1,000 calls, which is
most of the cost of each question.

### Perplexity

In the API console, open **API keys** and click **Generate API Key**. Add a
payment method and buy credits under **Billing**. Perplexity blocks keys when
credits run out. siteseoai uses the `sonar` model, priced at $1 per million tokens
in and out plus a request fee of $5 to $12 per 1,000 requests, depending on
search depth.

### What a run costs

The cost of a run is prompts times three times the number of providers. Ten
prompts with all three providers is 90 calls.

These calls are paid work under the same rule as DataForSEO below. Before any
call, siteseoai prints the estimated cost of the run and what remains of
`budget.monthly_usd` for the month, then waits for you to confirm. It refuses if
the budget is zero or the estimate would go over it, and if a run costs more
than estimated, it stops at the cap partway through.

The first estimate is a deliberately high placeholder, because the size of the
search results each assistant reads is unknown before the call. After each run,
siteseoai works out what every call actually cost from the usage figures in the
provider's response, records it in the site repository, and estimates later
runs from the median cost per call of the last ten. The provider's own billing
page remains the final word, and setting a spending limit there as well costs
nothing.

## Keyword and SERP research: DataForSEO

`/siteseoai research <term>` buys keyword and search result data from
[DataForSEO](https://dataforseo.com), paid per request with no subscription.

1. Register at [app.dataforseo.com](https://app.dataforseo.com/register). New
   accounts get $1 of trial credit. The minimum top-up after that is $50, and a
   balance does not expire.
2. Open the [API Access](https://app.dataforseo.com/api-access) page. It shows
   your API login and API password.
3. Store both:

   ```
   aihsm put SITESEOAI_DATAFORSEO_LOGIN
   aihsm put SITESEOAI_DATAFORSEO_PASSWORD
   ```

The API password is generated by DataForSEO and is not the password you log in
with. If the first call fails authentication, check that one first.

These calls are capped. Set `budget.monthly_usd` in `siteseoai.yaml`; it defaults
to zero, which turns paid research off. Every call prints its estimated cost and
what remains of the month, waits for you to confirm, and refuses if it would go
over the cap. Spend is recorded in the site repository.

Your own backlinks need no key. Export the Search Console links report, or an
Ahrefs free tier export, into `.siteseoai/imports/backlinks/`.

Sources:
[Anthropic API keys](https://platform.claude.com/docs/en/get-api-key),
[paying for Anthropic API usage](https://support.claude.com/en/articles/8977456-how-do-i-pay-for-my-claude-api-usage),
[Anthropic web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool),
[OpenAI quickstart](https://developers.openai.com/api/docs/quickstart),
[OpenAI pricing](https://developers.openai.com/api/docs/pricing#built-in-tools),
[Perplexity projects and billing](https://docs.perplexity.ai/docs/getting-started/projects),
[Perplexity pricing](https://docs.perplexity.ai/docs/getting-started/pricing),
[DataForSEO authentication](https://docs.dataforseo.com/v3/auth/),
[DataForSEO FAQ](https://dataforseo.com/faq).

---

Previous: [Bing Webmaster Tools](07-bing.md) | Next: [Troubleshooting](troubleshooting.md)

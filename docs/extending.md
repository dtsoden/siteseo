[Docs home](README.md) / What siteseo does not cover

# What siteseo does not cover, and how to extend it

Checked against official documentation on 2026-10-14.

siteseo stays as free as it can. Where measuring something would mean a paid
service or code against an unofficial interface, it is left out and written up
here instead. siteseo is MIT licensed, so if you want any of these, fork it and
add them; the notes below say where to start.

## Google AI Overviews and AI Mode

siteseo does not measure whether Google's AI answers cite your site.

Search Console has a Search generative AI performance report, announced on
[Google's Search Central blog](https://developers.google.com/search/blog/2026/06/gen-ai-performance-reports)
in June 2026, that counts how often your pages appeared in AI Overviews and AI
Mode. You can read it in Search Console itself. siteseo cannot,
because the Search Console API does not return it. The API's
[query reference](https://developers.google.com/webmaster-tools/v1/searchanalytics/query)
lists no type or filter for AI features, and a query grouped by
`searchAppearance` across ten properties on 2026-10-14 returned no AI values. If
Google adds it to the API, `scripts/gsc.py` is where it would go, using the
service account siteseo already has.

Google offers no API for asking AI Mode a question and reading its sources.
DataForSEO sells one: its
[Google AI Mode SERP API](https://docs.dataforseo.com/v3/serp/google/ai_mode/overview/)
returns the AI Mode answer with a `references` list of the pages it cited, at
[$0.0012 to $0.004 per query](https://dataforseo.com/pricing/google-serp/google-ai-mode-serp-api).
siteseo already holds DataForSEO credentials and a spend cap in
`scripts/dataforseo.py`, so a fork would add a call there and compare each
reference's domain with the site, the way `scripts/ai_probe.py` treats
citations.

## Microsoft Copilot

siteseo reads Copilot citations from the Bing AI Performance report, which you
export by hand as a CSV (see [Bing](setup/07-bing.md#the-ai-performance-report)).
Microsoft publishes no API for that report and none for asking consumer Copilot
a question, so siteseo does nothing more. Services that query Copilot by driving
its web interface exist, but they depend on an interface Microsoft can change at
any time, and siteseo does not build on them.

## Other assistants

AI visibility tracking asks Claude, ChatGPT and Perplexity through their paid
APIs, as described in [Paid keys](setup/08-paid-keys.md). Adding another
assistant with a search-enabled API means three entries in
`scripts/ai_probe.py`: its key and model in `PROVIDERS`, a function in `ASK`
that returns the answer text and cited URLs, and its list prices in `PRICES` so
the budget cap can count what it spends.

---

Previous: [Troubleshooting](setup/troubleshooting.md) | Back to [docs home](README.md)

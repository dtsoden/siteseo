[Docs home](../README.md) / [Setup guide](README.md) / Bing Webmaster Tools

# Bing Webmaster Tools

Checked against official documentation on 2026-10-14.

Bing gives siteseo two things Google does not. One is its own query, page and
crawl data through the Webmaster API. The other is the AI Performance report,
which shows when Microsoft Copilot and Bing's AI answers cited your pages and
the questions that led to it.

Bing uses a personal API key rather than a service account. One key covers
every site verified under your Bing account.

## 1. Add your site

Sign in to [Bing Webmaster Tools](https://www.bing.com/webmasters). If your
sites are already verified in Search Console, choose **Import sites from Google
Search Console**, select them and click **Import**. They arrive verified, with
no file or DNS record to add. Bing re-checks ownership through Search Console
from time to time.

Otherwise choose **Add your site manually** and verify with one of the four
methods Bing offers: an XML file (`BingSiteAuth.xml`) at the site root, a meta
tag, a CNAME record, or automatic DNS verification for supported DNS providers.

Data takes about 48 hours to appear after a site is added.

The site address in Bing has to match the `site` value in your `siteseo.yaml`,
including the protocol and any `www.`, because siteseo asks Bing for that exact
URL.

## 2. Generate an API key

1. Click **Settings** (the gear, top right).
2. Open **API Access**.
3. Accept the terms the first time, then choose **API Key**.
4. Click **Generate API Key** and copy it.

Bing allows one API key per user, so if you already generated one for another
tool, siteseo uses the same key. Microsoft's documentation dates these steps to
2022, so a label may have moved since. The key itself is still supported: when
Bing retired its older SOAP and POX endpoints on 2026-08-31, it stated that
existing API keys keep working, and siteseo uses the JSON endpoint that stayed.

Bing also offers OAuth and recommends it for apps acting on behalf of other
users. siteseo uses the key, because it only reads your own sites.

## 3. Store it

```
aihsm put SITESEO_BING_API_KEY
```

or any of the alternatives in [Storing secrets](02-secrets.md).

## The AI Performance report

This report has no API. Microsoft has not announced one, so it comes in as a
CSV export:

1. In Bing Webmaster Tools, open **AI Performance**.
2. Pick a date range (7 days, 30 days, 3 months or custom) and open the
   **Grounding Queries** tab.
3. Export to CSV.
4. Save the file in your site repository under `.siteseo/imports/bing-ai/`.

siteseo reads every CSV in that folder. Grounding queries are real questions
that already pulled your pages into an AI answer, which makes them the best
seed for the AI visibility prompts in [Paid keys](08-paid-keys.md). The report
is a daily sample rather than a complete log, and Microsoft still labels it a
preview.

Everything up to this page is free. The next page, Paid keys, is optional.

Sources:
[adding and verifying a site](https://www.bing.com/webmasters/help/add-and-verify-site-12184f8b),
[getting API access](https://learn.microsoft.com/en-us/bingwebmaster/getting-access),
[SOAP and POX deprecation](https://www.bing.com/webmasters/help/soap-pox-api-deprecation-s0appox01),
[AI Performance report](https://www.bing.com/webmasters/help/ai-performance-9f8e7d6c),
[AI Performance announcement](https://blogs.bing.com/webmaster/2026/2/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview/).

---

Previous: [PageSpeed and CrUX](06-pagespeed.md) | Next: [Paid keys](08-paid-keys.md)

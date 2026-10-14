[Docs home](../README.md) / Setup guide

# Setting up siteseo

Every step in this guide was checked against the vendor's own documentation on
2026-10-14. Google, Microsoft and the AI providers rename menus without notice,
so if a label on your screen differs from the one written here, the linked
official page is the one to trust. Each page links its sources.

Only the first page is required. With nothing else configured, siteseo still
crawls your build or live site and runs the on-page, structured data, AI crawler
and agent readiness checks, plus the pre-deploy gate. Every other page adds one
data source, and a missing one shrinks a run rather than failing it.

| Page | What it adds | Cost | Time |
| --- | --- | --- | --- |
| [Install](01-install.md) | the plugin and its Python environment | free | 5 minutes |
| [Storing secrets](02-secrets.md) | somewhere safe to keep the keys below | free | 5 minutes |
| [Google Cloud](03-google-cloud.md) | a service account and the APIs it calls | free | 15 minutes |
| [Search Console](04-search-console.md) | queries, clicks, impressions, index status | free | 2 minutes per site |
| [Google Analytics](05-analytics.md) | sessions, engagement, AI assistant referrals | free | 2 minutes |
| [PageSpeed and CrUX](06-pagespeed.md) | lab performance and real-user Core Web Vitals | free | 5 minutes |
| [Bing Webmaster Tools](07-bing.md) | Bing queries and crawl data, Copilot citations | free | 10 minutes |
| [Paid keys](08-paid-keys.md) | AI citation tracking, keyword and backlink research | per call | 10 minutes each |
| [Troubleshooting](troubleshooting.md) | the errors that cost real time during setup | | |

Do them in that order. Search Console and Analytics both need the Google Cloud
page done first, and PageSpeed uses the same Cloud project.

## Before you start

This guide assumes the accounts below already exist and work. siteseo reads
from them; it does not create them, and these pages do not walk through setting
them up. Each platform's own help pages do that, and they are the ones to
follow, because the steps depend on your domain registrar, your host and how
your site is built.

- A verified Search Console property for the site, with you as an owner.
  Adding a property and verifying it is done in Search Console, often through a
  DNS record at your domain registrar, and can take time to take effect. Google
  explains both:
  [Add a website property](https://support.google.com/webmasters/answer/34592)
  and [Verify your site ownership](https://support.google.com/webmasters/answer/9008080).
  A Domain property can only be verified through DNS. Only an owner can give
  siteseo access, so if someone else set the property up, they need to add you
  as an owner or do the Search Console step for you.
- A Google Analytics 4 property collecting data for the site, with you as an
  Administrator. That means an account, a property, a web data stream and the
  Google tag installed on every page. Google explains it in
  [Set up Analytics for a website and/or app](https://support.google.com/analytics/answer/9304153).
  Without GA4, skip the Analytics page; everything else still works.
- Python 3.11 or newer on your PATH. siteseo uses it only to start, and
  builds its own isolated environment from there.

Bing needs nothing in advance once the Search Console property exists, because
Bing can import your sites straight from it. Without Search Console, Bing's own
[add and verify a site](https://www.bing.com/webmasters/help/add-and-verify-site-12184f8b)
page covers its other methods.

If any of these is missing, siteseo still runs. The modules that need it report
themselves as skipped and say what would enable them.

Some things siteseo deliberately does not measure, such as citations in
Google's AI answers. [What siteseo does not cover](../extending.md) lists them
and what it would take to add each one.

## What it looks like when it's done

```
/siteseo doctor
```

Every secret you set up shows `ok`. Then, inside a site repository:

```
/siteseo pull
```

Search Console reports clicks and impressions, Analytics reports sessions, and
Bing reports its query data. If any of them says nothing, the
[troubleshooting page](troubleshooting.md) covers each failure in turn.

---

Next: [Install](01-install.md)

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

You need to already own the things siteseo reads. It does not create them.

- A Search Console property for the site, verified. Google's
  [verification guide](https://support.google.com/webmasters/answer/9008080)
  covers the methods. You must be an owner of the property to give siteseo
  access to it.
- A Google Analytics 4 property collecting data for the site, with you as an
  Administrator on its account. Without one, skip the Analytics page.
- Python 3.11 or newer on your PATH. siteseo uses it only to start, and builds
  its own isolated environment from there.

The Bing page needs nothing in advance, because Bing can import your sites
straight from Search Console.

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

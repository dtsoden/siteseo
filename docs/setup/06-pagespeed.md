[Docs home](../README.md) / [Setup guide](README.md) / PageSpeed and CrUX

# PageSpeed Insights and CrUX

Checked against official documentation on 2026-10-14.

Module D uses two Google APIs with one API key. PageSpeed Insights runs
Lighthouse against each template URL in your config and returns lab
measurements. The Chrome UX Report API returns field data: Core Web Vitals
measured from real Chrome users visiting your site over the last 28 days. Lab
data says what could be slow. Field data says what visitors actually got.

An API key is a different credential from the service account. It identifies
your Cloud project and nothing else, and it goes in the same project you made
on the [Google Cloud](03-google-cloud.md) page.

## 1. Enable both APIs

In the API Library, enable:

- [PageSpeed Insights API](https://console.cloud.google.com/apis/library/pagespeedonline.googleapis.com)
- [Chrome UX Report API](https://console.cloud.google.com/apis/library/chromeuxreport.googleapis.com)

Each is a separate switch. On 2026-10-14 a key from a project with only the
first enabled worked for PageSpeed and got a 403 from CrUX saying the API "has
not been used in project ... before or it is disabled". siteseoai reports that as
`perf.crux_unavailable` with Google's message, so it reads as a setup problem
rather than a quiet site.

## 2. Create the key

1. Open **APIs and Services**, then
   [Credentials](https://console.cloud.google.com/apis/credentials).
2. Click **Create credentials**, then **API key**.
3. Under API restrictions, select **PageSpeed Insights API** and **Chrome UX
   Report API**. Google now requires at least one restriction when a key is
   created in the console.
4. Leave **Authenticate API calls through a service account** unticked.
5. Click **Create** and copy the key.

Google's
[API key guidance](https://docs.cloud.google.com/docs/authentication/api-keys-best-practices)
also recommends an application restriction. Of the four types, **IP addresses**
is the one that fits a tool running on your own machine or a CI runner, if those
have fixed addresses. The **Websites** type checks the browser's referrer
header, which siteseoai's requests do not send, so it would block them.

## 3. Store it

```
aihsm put SITESEOAI_PAGESPEED_API_KEY
```

or any of the alternatives in [Storing secrets](02-secrets.md).

## Limits and cost

CrUX allows 150 queries a minute per Cloud project, documented as free with no
paid tier. Google publishes no price and no fixed quota for PageSpeed Insights
on its documentation pages; the current quota for your project is on the API's
**Quotas** page in Cloud Console. siteseoai makes one CrUX call per run and two
PageSpeed calls per template URL (mobile and desktop), so a handful of
templates stays well inside both.

CrUX only has data for origins with enough Chrome traffic. A new or quiet site
gets no field data even with everything configured, and siteseoai reports that
as a notice.

Sources:
[PageSpeed Insights API, get started](https://developers.google.com/speed/docs/insights/v5/get-started),
[CrUX API](https://developer.chrome.com/docs/crux/api),
[managing API keys](https://docs.cloud.google.com/docs/authentication/api-keys),
[securing API keys](https://docs.cloud.google.com/docs/authentication/api-keys-best-practices).

---

Previous: [Google Analytics](05-analytics.md) | Next: [Bing Webmaster Tools](07-bing.md)

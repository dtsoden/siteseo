[Docs home](../README.md) / [Setup guide](README.md) / Search Console

# Search Console

Checked against official documentation on 2026-10-14.

Search Console grants access per property, and there is no account-wide
equivalent. Do this once for every site you want siteseo to read, including
each new site you add later. Nothing in Google Cloud changes when you add a
site: the account and its key stay as they are, and the new site needs only
this grant.

You must be an owner of the property. Only owners see the menu used below.

## Add the service account

1. Open [Search Console](https://search.google.com/search-console) and select
   the property.
2. Go to **Settings**, then **Users and permissions**.
3. Click **Add user** and paste the service account's email.
4. Choose **Restricted** and click **Add**.

Restricted is enough. siteseo only reads, and on 2026-10-14 a service account
with Restricted permission successfully ran both the Search Analytics query and
the URL Inspection API calls siteseo makes. Choose **Full** only if you want
that account able to take actions in Search Console as well.

Google's
[permissions page](https://support.google.com/webmasters/answer/7687615)
describes what each level can do in the web interface, and its table lists URL
Inspection as "Fetch only" for Restricted users. That table covers the
interface. It says nothing about the API, which is why the test above was run.

## Domain properties cover more

A Domain property, such as `sc-domain:example.com`, covers every subdomain and
both http and https. A URL-prefix property, such as `https://www.example.com/`,
covers only that exact protocol and host. If you own several subdomains, one
Domain property and one grant covers them all. Domain properties can only be
verified through DNS.

siteseo tries the URL-prefix property for your `site` address first, then the
Domain property with and without `www.`, so whichever you have works without
configuration.

## Check it

```
"${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run gsc.py --whoami
```

This prints the service account's email, its Cloud project, every property it
can read with the permission level on each, and whether the site in the current
repository is one of them. If the site is missing, the grant above was not
saved. The command exits non-zero in that case and names the email to paste, so
a deploy script can use it as a check.

## Quotas

Google's published limits are 2,000 URL Inspection calls a day and 600 a minute
per property, and 1,200 Search Analytics queries a minute per site. siteseo
inspects at most 40 URLs per pull, so a daily run stays far inside them.

If adding the email fails, see
[troubleshooting](troubleshooting.md#search-console-or-analytics-rejects-the-service-account-email).


Sources:
[managing users and permissions](https://support.google.com/webmasters/answer/7687615),
[property types](https://support.google.com/webmasters/answer/34592),
[verifying ownership](https://support.google.com/webmasters/answer/9008080),
[usage limits](https://developers.google.com/webmaster-tools/limits).

---

Previous: [Google Cloud](03-google-cloud.md) | Next: [Google Analytics](05-analytics.md)

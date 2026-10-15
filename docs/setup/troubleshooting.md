[Docs home](../README.md) / [Setup guide](README.md) / Troubleshooting

# Troubleshooting

Checked against official documentation on 2026-10-14.

Each of these cost real time during setup, and most are not in Google's
documentation anywhere you would look first.

## Three 403s that look alike and are not

A 403 saying *"... API has not been used in project N before or it is
disabled"* means an API is switched off in your Cloud project. The message names
the API and includes a link to enable it. Enable it, wait a few minutes, and run
again. The four siteseo needs are listed on the
[Google Cloud page](03-google-cloud.md#2-enable-four-apis). The Analytics Admin
API and the Chrome UX Report API are the two usually missed.

A 403 saying *"Requests to this API ... are blocked"* means the API is enabled
but your API key's restrictions leave it out. In Cloud Console open **APIs and
Services**, **Credentials**, select the key, add the API under **API
restrictions** and save. This is the usual second error after enabling the
Chrome UX Report API, because the PageSpeed key was restricted before CrUX was
switched on.

A 403 saying *"User does not have sufficient permission"* means the service
account was never added as a user in Search Console or Analytics, or was added
to a different property. That is fixed inside the product, not in Cloud
Console. See [Search Console](04-search-console.md) and
[Google Analytics](05-analytics.md).

## Search Console or Analytics rejects the service account email

Since April 2026, Search Console and Analytics have intermittently refused to
add newly created service accounts, saying the email does not match a Google
account. Ordinary Gmail addresses work in the same dialog. Reports in the
[Google developer forum](https://discuss.google.dev/t/problem-with-new-service-accounts/362176)
show it easing in June and returning on 2026-09-14, and Google has not
responded there. Until it does:

- Wait a few hours after creating the service account and try again. For
  Search Console, that delay has been enough for most people reporting it.
- For Analytics, an Administrator can add the account through the Admin API
  instead of the dialog, by creating an access binding with the Viewer role.
  Google's
  [accessBindings reference](https://developers.google.com/analytics/devguides/config/admin/v1/rest/v1alpha/properties.accessBindings/create)
  documents the call. It needs a user OAuth token with the
  `analytics.manage.users` scope, which the
  [OAuth Playground](https://developers.google.com/oauthplayground) can issue.

## "Failed to register users" in Analytics

When siteseo was first set up, adding a service account in Analytics with
**Notify new users by email** ticked failed with this error, and unticking the
box fixed it. The error says nothing about email. Google does not document the
link, but a service account has no mailbox, so leave the box unticked in any
case.

## Service account key creation is disabled

Your project sits under an organization that enforces Google's default policy
against downloadable keys. See
[If key creation is blocked](03-google-cloud.md#if-key-creation-is-blocked).

## The report says the Chrome UX Report API refused the request

That is finding `perf.crux_unavailable`, and it carries Google's own error
message. "Has not been used in project" means the API is off. "Are blocked"
means it is on but missing from the key's API restrictions. Fix whichever it
names, as on [PageSpeed and CrUX](06-pagespeed.md). A plain "no field data"
notice is different: the API answered and simply has no data for your origin.

## Analytics reports the wrong site

siteseo picks the GA4 property whose name contains your site's hostname. If no
name matches, it uses the first property it can see and prints which one. Rename
the property in Analytics (**Admin**, **Property details**) to include the
domain.

## Bing returns nothing

"The Bing Webmaster API did not answer" means the key was rejected or the site
URL did not match. The `site` value in `siteseo.yaml`, including `https://` and
any `www.`, has to be exactly the site as added in Bing Webmaster Tools. A site
added in the last 48 hours may also have no data yet.

## doctor says ok but a tool says the secret is missing

Doctor checks your vault and environment. The tools receive secrets only when
started through siteseo's launcher, which wraps them in `aihsm run`. Run tools as
`"${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run <script>.py`, not with a bare
`python`. If you use a password manager instead of aihsm, start Claude Code
through it so the variables are in the session.

## Months later, when you have forgotten all of this

Two things go missing from memory: which service account you made, and whether
a particular site was ever granted to it. Ask siteseo:

```
"${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run gsc.py --whoami
```

```
Search Console access

  service account  seo-agent@your-project.iam.gserviceaccount.com
  cloud project    your-project
  this site        sc-domain:example.com (readable)

  3 property(ies) this account can read:
    sc-domain:example.com  (siteFullUser)
    https://another.example/  (siteRestrictedUser)
    sc-domain:third.example  (siteRestrictedUser)
```

The email is read from the key file and is not a secret; the private key beside
it is never read. If the site in this repository is missing from the list, it
was never granted. Add the email in Search Console under **Settings**, **Users
and permissions**, as Restricted. The command exits non-zero in that case and
names the email to paste, so a deploy script can use it as a check.

Sources:
[Google API error format](https://developers.google.com/data-manager/api/devguides/concepts/understand-errors),
[troubleshooting organization policies](https://docs.cloud.google.com/iam/docs/troubleshoot-org-policies),
[Search Console users and permissions](https://support.google.com/webmasters/answer/7687615),
[Analytics access](https://support.google.com/analytics/answer/9305587).

---

Previous: [Paid keys](08-paid-keys.md) | Next: [Your first report](../first-report.md)

[Docs home](../README.md) / [Setup guide](README.md) / Google Analytics

# Google Analytics

Checked against official documentation on 2026-10-14.

Analytics lets you grant access once for a whole account, and every GA4 property
under that account inherits it. If all your sites sit under one Analytics
account, this is a single grant that covers them all, including sites you add
later.

You need the Administrator role on the Analytics account to add users.

## Add the service account

1. Open [Google Analytics](https://analytics.google.com) and click **Admin**.
2. Under the **Account** settings, open **Account access management**. Use the
   account-level page, not **Property access management** under the property
   settings, unless you want to grant one property only.
3. Click **+**, then **Add users**.
4. Paste the service account's email.
5. Untick **Notify new users by email**. A service account has no mailbox.
6. Choose the **Viewer** role and click **Add**.

Viewer is enough. It lets the account read report data through the Analytics
Data API and list the properties it can see through the Admin API, which is all
siteseoai does. Google's
[roles page](https://support.google.com/analytics/answer/9305587) describes the
other roles.

If your sites are spread across several Analytics accounts, repeat this once
per account.

## How siteseoai finds your property

You never paste a property ID. siteseoai asks the Admin API which properties the
service account can see and picks the one whose name contains your site's
hostname. If none matches, it uses the first one it finds and says so in the
output, listing what it could see. Naming each GA4 property after its domain
keeps the match reliable.

## Check it

In a site repository:

```
/siteseoai pull
```

Analytics should report sessions. If it says the service account can see no
properties, the grant above did not save. If it reports a 403 mentioning
`analyticsadmin.googleapis.com`, the Admin API is not enabled in your Cloud
project (step 2 of [Google Cloud](03-google-cloud.md)).

If the Add users dialog rejects the email, see
[troubleshooting](troubleshooting.md#search-console-or-analytics-rejects-the-service-account-email).

Sources:
[adding users](https://support.google.com/analytics/answer/9305788),
[access and roles](https://support.google.com/analytics/answer/9305587),
[accountSummaries.list](https://developers.google.com/analytics/devguides/config/admin/v1/rest/v1beta/accountSummaries/list),
[runReport](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runReport).

---

Previous: [Search Console](04-search-console.md) | Next: [PageSpeed and CrUX](06-pagespeed.md)

[Docs home](../README.md) / [Setup guide](README.md) / Google Cloud

# Google Cloud: project, service account, APIs

Checked against official documentation on 2026-10-14.

One service account reads both Search Console and Analytics, and the same Cloud
project holds the PageSpeed key. You do this page once, however many sites you
add later.

Google documents the Search Console API and the Chrome UX Report API as free of
charge, and publishes quotas rather than prices for the Analytics and PageSpeed
APIs.

## 1. Create a project

In [Google Cloud Console](https://console.cloud.google.com), open the
[Manage resources](https://console.cloud.google.com/cloud-resource-manager) page
and click **Create project**. Give it a name, leave the billing account empty if
asked, choose a parent organization or **No organization**, and click
**Create**.

## 2. Enable four APIs

With the new project selected, open each of these in the API Library and click
**Enable**. Each one is a separate switch, and siteseoai calls all four.

| API | Library page | Used for |
| --- | --- | --- |
| Google Search Console API | [searchconsole.googleapis.com](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com) | queries, clicks, URL Inspection |
| Google Analytics Data API | [analyticsdata.googleapis.com](https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com) | sessions and engagement reports |
| Google Analytics Admin API | [analyticsadmin.googleapis.com](https://console.cloud.google.com/apis/library/analyticsadmin.googleapis.com) | finding which GA4 property belongs to your site |
| Chrome UX Report API | [chromeuxreport.googleapis.com](https://console.cloud.google.com/apis/library/chromeuxreport.googleapis.com) | real-user Core Web Vitals, see [PageSpeed](06-pagespeed.md) |

The Admin API is the one people skip. siteseoai uses it to list the Analytics
properties the service account can see and match one to your site, so you never
have to paste a property ID. Without it, Analytics fails with a 403 saying the
API "has not been used in project ... before or it is disabled".

Google says to allow a few minutes after enabling an API before calling it.

## 3. Create the service account

Open **IAM and Admin**, then
[Service accounts](https://console.cloud.google.com/iam-admin/serviceaccounts),
and click **Create service account**.

1. Enter a name such as `siteseoai`. The ID is generated from it and cannot be
   changed later.
2. Click **Create and continue**.
3. The permissions step is marked optional. Skip it. Project roles control
   access to Cloud resources and have nothing to do with Search Console or
   Analytics, which grant access inside their own admin screens.
4. Click **Done**.

Copy the account's email from the list. It looks like
`siteseoai@your-project.iam.gserviceaccount.com`, and you paste it into Search
Console and Analytics next.

## 4. Create a JSON key

Click the account's email, open the **Keys** tab, choose **Add key**, then
**Create new key**, select **JSON** and click **Create**. The file downloads
once, and Google keeps no copy.

Move it out of your downloads folder to somewhere outside any repository, then
store its path (not its contents) as `SITESEOAI_GSC_SERVICE_ACCOUNT`:

```
aihsm put SITESEOAI_GSC_SERVICE_ACCOUNT
```

and paste the full path when prompted. [Storing secrets](02-secrets.md) covers
the alternatives to aihsm.

### If key creation is blocked

Google enforces a policy named `iam.disableServiceAccountKeyCreation` by default
on every organization created on or after May 3, 2024. If your project sits
under one of those, the console shows **Service account key creation is
disabled** instead of a key.

Someone with the **Organization Policy Administrator** role has to lift it,
either for the whole organization or for this one project. Google's
[troubleshooting page](https://docs.cloud.google.com/iam/docs/troubleshoot-org-policies)
gives both methods. Google's documentation names the constraint two ways,
`iam.disableServiceAccountKeyCreation` and
`iam.managed.disableServiceAccountKeyCreation`, so search for both in the
Organization Policies page.

A Google account that has never created an organization usually puts projects
under **No organization**, where the policy does not apply. Google's
documentation also says new free-trial signups now get a standalone
organization created for them, and it does not say whether that organization
blocks keys. If you are on a new account and see the block, you are that
organization's administrator and can lift it yourself.

## 5. Grant it access

The key proves who the account is. It does not grant access to anything, and
this is the step most often missed. Each product grants access in its own admin
screen:

- [Search Console](04-search-console.md), once per site.
- [Google Analytics](05-analytics.md), once per Analytics account.

Sources:
[creating projects](https://docs.cloud.google.com/resource-manager/docs/creating-managing-projects),
[creating service accounts](https://docs.cloud.google.com/iam/docs/service-accounts-create),
[creating keys](https://docs.cloud.google.com/iam/docs/keys-create-delete),
[security baseline constraints](https://docs.cloud.google.com/resource-manager/docs/manage-baseline-constraints),
[standalone organizations](https://docs.cloud.google.com/resource-manager/docs/standalone-organization-overview),
[Analytics Admin API quickstart](https://developers.google.com/analytics/devguides/config/admin/v1/quickstart),
[enabling APIs](https://docs.cloud.google.com/apis/docs/getting-started).

---

Previous: [Storing secrets](02-secrets.md) | Next: [Search Console](04-search-console.md)

# siteseo documentation

Checked against official documentation on 2026-10-14.

Start with the setup guide and work down the list. Every page links back here
at the top and to the page before and after it at the bottom.

## Setup

The [setup guide](setup/README.md) explains what each step adds, what it costs
and what has to exist before you start. Only the first page is required.

1. [Install](setup/01-install.md): the plugin and its Python environment.
2. [Storing secrets](setup/02-secrets.md): where siteseo reads keys from.
3. [Google Cloud](setup/03-google-cloud.md): a project, a service account and
   the four APIs siteseo calls.
4. [Search Console](setup/04-search-console.md): give the service account
   access to each site.
5. [Google Analytics](setup/05-analytics.md): give it access to your GA4
   account.
6. [PageSpeed and CrUX](setup/06-pagespeed.md): an API key for performance data.
7. [Bing Webmaster Tools](setup/07-bing.md): Bing data and Copilot citations.
8. [Paid keys](setup/08-paid-keys.md): optional AI citation tracking and keyword
   research, with a spending cap.

## When something fails

[Troubleshooting](setup/troubleshooting.md) covers the errors that cost real
time during setup, with the exact message each one shows.

## Beyond siteseo

[What siteseo does not cover](extending.md) lists what is left out on purpose,
such as citations in Google's AI answers, and how a fork could add each one.

---

Next: [Setup guide](setup/README.md)

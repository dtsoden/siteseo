# Storing secrets

Checked against official documentation on 2026-10-14.

siteseo reads every credential from an environment variable named in the table
below. It never reads a value from `siteseo.yaml` or from any file in your
repository, and `/siteseo doctor` reports which names resolve on this machine
without printing a value.

| Variable | Holds | Set up on |
| --- | --- | --- |
| `SITESEO_GSC_SERVICE_ACCOUNT` | the path to a JSON key file, not its contents | [Google Cloud](03-google-cloud.md) |
| `SITESEO_PAGESPEED_API_KEY` | a Google API key | [PageSpeed](06-pagespeed.md) |
| `SITESEO_BING_API_KEY` | a Bing Webmaster API key | [Bing](07-bing.md) |
| `SITESEO_ANTHROPIC_API_KEY` | an Anthropic API key | [Paid keys](08-paid-keys.md) |
| `SITESEO_OPENAI_API_KEY` | an OpenAI API key | [Paid keys](08-paid-keys.md) |
| `SITESEO_PERPLEXITY_API_KEY` | a Perplexity API key | [Paid keys](08-paid-keys.md) |
| `SITESEO_DATAFORSEO_LOGIN` | your DataForSEO API login | [Paid keys](08-paid-keys.md) |
| `SITESEO_DATAFORSEO_PASSWORD` | your DataForSEO API password | [Paid keys](08-paid-keys.md) |

Any tool that puts those variables into the environment works. Pick one.

## aihsm, the OS vault

[aihsm](https://github.com/dtsoden/aihsm) keeps secrets in Windows Credential
Manager, macOS Keychain or the Linux Secret Service, and injects them into a
child process instead of printing them. siteseo's launcher detects it and wraps
every tool in `aihsm run` automatically, so there is nothing to configure beyond
storing the values.

Install it from its repository (Python 3 required; Linux also needs GNOME
Keyring or KWallet):

```
git clone https://github.com/dtsoden/aihsm.git
cd aihsm
bash install.sh        macOS and Linux
.\install.ps1          Windows
```

Then store each secret by name. The value is typed at a hidden prompt, twice,
and never passed on the command line:

```
aihsm put SITESEO_PAGESPEED_API_KEY
aihsm list
```

`aihsm list` prints names only.

## A password manager

1Password's CLI injects secrets into a process from an env file of references:

```
# siteseo.env, safe to keep because it holds references, not values
SITESEO_PAGESPEED_API_KEY="op://Private/siteseo/pagespeed"
```

```
op run --env-file=siteseo.env -- claude
```

Bitwarden's Secrets Manager CLI does the same with `bws run -- claude`, naming
each variable after the secret's key. Bitwarden's password manager CLI, `bw`,
has no equivalent, so it will not work here.

Whichever you use, start Claude Code through it so the variables exist in the
session siteseo runs in.

## A plain environment variable

Exported in your shell profile. It's the least protected option, since any
process you run can read it, but it is still far better than a file in a
repository.

## Keep the Google key file out of every repository

`SITESEO_GSC_SERVICE_ACCOUNT` holds a path, and the file at that path is a live
credential. Google names the download after your project plus a random suffix,
something like `my-project-8f3a91c2e4d7.json`, which no gitignore pattern
predicts. Left in a working directory it is one `git add -A` away from being
published.

Google's own
[key management guidance](https://docs.cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys)
says to never commit keys, not to leave copies in your downloads folder, and to
rotate them. It also advises against keeping service account keys in Google
Secret Manager. Move the file to a folder outside any repository, such as
`~/.config/siteseo/`, and store that path.

If a key ever is committed, delete it in Cloud Console (the service account's
**Keys** tab) and create a new one. Rewriting git history does not make a
published key safe again.

Next: [Google Cloud](03-google-cloud.md).

Sources:
[aihsm README](https://github.com/dtsoden/aihsm),
[1Password op run](https://www.1password.dev/cli/reference/commands/run/),
[1Password secret references](https://www.1password.dev/cli/secrets-environment-variables/),
[Bitwarden Secrets Manager CLI](https://bitwarden.com/help/secrets-manager-cli/),
[Google service account key management](https://docs.cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys).

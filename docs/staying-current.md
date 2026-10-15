[Docs home](README.md) / Staying current

# Staying current

Two clocks drift independently and both are tracked.

Vendored code is pinned in `upstream.lock` by commit and content hash. The
reference data carries `last_verified` dates, because crawler names and rich
result rules change without any repository moving. A weekly job checks both and
opens one pull request showing exactly what moved and what has passed ninety
days. Nothing executes on any machine until you read that diff and merge it.

Cloudflare's agent readiness scanner is a third clock. Its source is not public,
but each check it runs ships a skill file with a published digest, and those
digests are pinned in `agent-readiness.yaml`. When one changes, appears or
disappears, the same weekly pull request names it, because that is usually the
first public sign that a check's criteria moved.

`/siteseoai doctor` warns locally when a pin is behind or a reference file has gone
stale. Continuous integration also re-checks every source URL in the check
catalog on a schedule, because documentation sites reorganise. Google moved its
crawling documentation to a new path during this project's first day, which is
exactly why that check exists.

---

Previous: [What it does not check](not-checked.md) | Next: [What siteseoai does not cover](extending.md)

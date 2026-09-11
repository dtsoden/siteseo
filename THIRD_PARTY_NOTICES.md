# Third party notices

siteseo is MIT licensed. It includes material from the projects below, each also
MIT licensed, pinned by commit and content hash in `upstream.lock` and verified
by `scripts/sync_upstream.py`.

## addyosmani/web-quality-skills

- Source: https://github.com/addyosmani/web-quality-skills
- Licence: MIT, reproduced at `vendor/web-quality-skills/LICENSE`
- Vendored: `skills/core-web-vitals/SKILL.md`, `skills/performance/SKILL.md`,
  `skills/seo/SKILL.md`

Used as reference material the model reads when judging modules B and D. These
are documents, not code, and nothing from this project is executed by siteseo.
`skills/siteseo/reference/perf-guidance.md` summarises them and points at the
vendored copies.

## agricidaniel/claude-seo

- Source: https://github.com/agricidaniel/claude-seo
- Licence: MIT, reproduced at `vendor/claude-seo/LICENSE`
- Vendored: the licence only

The cross-platform launcher in `scripts/siteseo` is an original implementation
whose discovery approach is adapted from that project's `scripts/claude-seo`:
find a bootstrap interpreter using only shell built-ins, honour an explicit
override as a single argument rather than a shell string, try the Windows `py`
launcher before bare interpreter names, and keep the launcher in `scripts/`
because hosted marketplaces reject a plugin shipping a top-level `bin/`. The
attribution is owed for the approach even though no file is copied.

No other code from that project is present or executed here. Its `seo-geo` skill
carries a Socket critical verdict on skills.sh and was deliberately not vendored.

## Runtime dependencies

Installed into an isolated environment by `siteseo setup`, never bundled in this
repository. Each keeps its own licence.

| Package | Purpose |
| --- | --- |
| selectolax | HTML parsing |
| httpx | HTTP requests |
| extruct, w3lib | JSON-LD, Microdata and RDFa extraction |
| PyYAML | configuration and reference files |
| google-api-python-client, google-auth | Search Console and URL Inspection |
| playwright | rendered DOM comparison, optional |
| cryptography | certificate expiry checks |

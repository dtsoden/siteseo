[Docs home](README.md) / Findings and fixes

# Findings and fixes

A list of defects is not a decision. Two things turn one into the other.

Findings are ranked by the traffic they affect, not by severity alone. Once
Search Console and Analytics are connected, a warning on a page earning 900
impressions outranks an error on a page nobody has ever reached. Severity still
matters, it multiplies rather than being replaced, so an error on a quiet page
still beats a notice on a busy one. Without those two connected, ordering falls
back to severity and the report says so, because a confident ranking built on no
data is worse than an honest unranked list.

Every audit saves two reports. The Markdown one is for whoever maintains the
site's code. The HTML one is for the person who owns the site: each problem is
named in plain English, repeats are grouped into one item with a page count, and
the site's own logo sits at the top, so it can be handed to a client or a
manager as it is. `/siteseo report --pdf` saves it as a PDF too, using the
Chromium that `siteseo setup --chromium` installs.
[See an example](https://siteseo.davidsoden.com/example-report).

The report ends with a brief for whoever maintains the site. siteseo does not
know your templating language, your voice, or why a page exists. The agent
working in that repository does. So the last section states, for each finding
worth acting on: what is wrong, the fix, how much traffic it touches, whether
it needs judgement, and the source backing the rule. It also lists what is
already working, the pages earning clicks and whether AI assistants send anyone,
because protecting those matters as much as fixing defects.

## Mechanical fixes and content are separated deliberately

`/siteseo fix` writes **mechanical SEO only: structure, attributes and
configuration, where the correct value follows from a rule. robots.txt generated
from your policy, canonical tags, image dimensions, sitemap entries, hreflang
codes, redirect rules, schema properties, an IndexNow key.

It never writes content**. A title, a description, alt text, a heading, a
rewrite. Those are words, and the right words depend on what the page is for and
how the site sounds. They go to the brief instead, for a human or the site's own
agent to decide. A tool that rewrites your titles because they are four
characters too long has misunderstood its job.

## Fix mode

`fix` prints diffs and writes nothing until you pass `--apply`. It edits source
templates and configuration, never built HTML, because editing `dist/` produces a
file the next build silently overwrites. That looks like a fix and is not one.

Where it cannot locate the source with confidence, it says what to change and
stops rather than guessing at a templating language it cannot verify. A tool that
half-understands your Astro components will produce a broken build, not a fixed
page.

---

Previous: [Configuration](configuration.md) | Next: [The pre-deploy gate](gate.md)

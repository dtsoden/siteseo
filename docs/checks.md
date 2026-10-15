[Docs home](README.md) / What it checks

# What it checks

168 checks across fourteen modules. Every one is declared in
`skills/siteseoai/reference/checks.yaml` with its severity, which score it counts
against, the rule, a source URL backing that rule, the fix, and whether the fix
can be applied automatically. 50 are automatically fixable.

| Module | Area | Checks |
| --- | --- | --- |
| A | Crawl and indexability | 43 |
| B | On-page | 24 |
| C | Structured data | 9 |
| D | Performance | 10 |
| E | AI crawler access | 8 |
| F | Content quality | 9 |
| G | Internal linking | 5 |
| H | International | 5 |
| I | Local | 3 |
| J | Search performance data | 4 |
| K | AI visibility | 4 |
| L | Research, paid | 1 |
| M | Backlinks | 2 |
| N | Analytics | reads only |
| O | Agent readiness | 41 |

Modules H and I stay off unless the site shows the signal, so a site with no
hreflang never gets advice about hreflang. Module O works the same way through
a profile: a content site is never told to build an OAuth server.

Two things here are unusual enough to call out.

Module E tests each AI crawler three ways, because the three can disagree and
the disagreement is usually the finding. It evaluates robots.txt rules for the
crawler's token under RFC 9309 precedence, fetches pages sending that crawler's
user-agent string, and compares both against the policy you declared. It also
diffs the robots.txt served live against the one in your repository, which is how
a content delivery network rewriting it gets caught. Anthropic and OpenAI
each run separate crawlers for training, search indexing and user-triggered
fetches, and blocking the training one does not block the others.

The two scores are never combined. Search health and AI access move
independently. A site can be technically excellent and invisible to assistants
because a firewall rule refuses them, or wide open to every crawler while its
canonical tags contradict its sitemap. Averaging those into one number destroys
the only information worth having. Both formulas are written out in
`reference/scoring.md` and printed next to the numbers, so a score can be argued
with.

---

Previous: [Where your data lives](data.md) | Next: [Agent readiness](agent-readiness.md)

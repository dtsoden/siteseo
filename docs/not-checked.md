[Docs home](README.md) / What it does not check

# What it does not check, and why

Every item here is a deliberate exclusion with a reason, not a gap.

## No traffic estimates for domains you do not own

Every vendor number for
those is modeled from clickstream panels, not measured. Presenting a model as a
measurement is the single most misleading thing SEO tooling does.

## No full backlink index

Building one is not feasible at this scale. Your own
links come free from the
[Search Console links report](https://support.google.com/webmasters/answer/9049606)
and Ahrefs free tier exports, imported as CSV. Only competitor links need a paid
call, and only when you ask.

## No toxic-link scores and no generated disavow files

Google's
[own guidance](https://support.google.com/webmasters/answer/2648487)
is that most sites should never use the disavow tool. siteseoai mentions disavow
only when Search Console reports a manual action.

## No single blended AI visibility score

Assistant answers change between runs,
accounts and locations. siteseoai reports a citation rate with its sample size and
the change since the last run. A rate without an n is not a measurement.

## No llms.txt scoring

It is reported present or absent at notice level and
affects neither score. Google's
[generative AI guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)
says it is not needed, and the
[Ahrefs study](https://ahrefs.com/blog/llmstxt-study/) found no effect.
`/siteseoai markdown --llms-txt` will write one from your exported pages if you
want an index for agents that look for it, but siteseoai never suggests it.

## No FAQPage or HowTo recommendations

Google
[narrowed FAQ rich results to a small set of sites and dropped HowTo entirely in
2023](https://developers.google.com/search/blog/2023/08/howto-faq-changes).
Pages that already carry the markup get a notice saying so.

## No Google-specific AI markup or content chunking advice

Google's generative
AI guide states that AI Overviews and AI Mode run on core Search ranking and
quality systems. There is nothing extra to add for them beyond ordinary SEO.

## No keyword density, LSI keywords, or similar folklore

## No PPC, social scheduling, or bulk content generation

## No automated content rewrites, page deletions, or noindex changes

Those are
judgement calls. siteseoai describes what it would change and stops.

## One honest limit

One honest limit, which is a property of the method rather than a choice. A 200
response to a spoofed user-agent string proves only that robots rules and
user-agent filtering did not block that request. Some operators verify crawler IP
ranges, so the real crawler could still be refused. Only bot-hit logs confirm
actual access, which is why module K reads them. Wherever this check appears, the
report says so.

Some things siteseoai leaves out because measuring them needs a paid service or
an unofficial interface. [What siteseoai does not cover](extending.md) lists those
and how a fork could add them.

---

Previous: [Agent readiness](agent-readiness.md) | Next: [Staying current](staying-current.md)

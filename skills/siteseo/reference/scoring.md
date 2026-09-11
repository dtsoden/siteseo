# Scoring

last_verified: 2026-09-11

siteseo keeps two scores and never combines them. Averaging them would hide the
only thing worth knowing, because they move independently. A site can be
technically excellent and invisible to AI assistants because a content delivery
network refuses their crawlers. Another can be wide open to every crawler while
its canonical tags contradict its sitemap. One number cannot say which you have.

Both formulas are printed next to the numbers they produce, so a score can be
argued with. A score nobody can reconstruct is a score nobody should trust.

## Search health

Start from the share of checked URLs carrying no error-severity finding in
modules A through D, then subtract a small amount for each distinct warning
type.

```
clean_share = (urls_checked - urls_with_errors) / urls_checked * 100
deduction   = min(distinct_warning_types * 1.5, 30)
score       = max(0, clean_share - deduction)
```

Warnings are counted per type rather than per URL. One template bug that touches
forty pages is one problem to fix, so it costs 1.5 once rather than 60. The
deduction is capped at 30 so warnings alone can never drive the score to zero
while errors are what actually block a deploy.

Only findings whose `score` field is `search` or `both` count. Findings marked
`none`, such as thin-content notices, are reported and never scored.

## AI access

Start from the share of policy-allowed crawlers that pass every module E test,
then subtract for main content that only exists after JavaScript runs.

```
allowed     = crawlers your ai_policy says should be allowed
passing     = allowed crawlers where robots.txt permits AND no sampled fetch was refused
share       = passing / allowed * 100
js_penalty  = 25 * (js_dependent_pages / pages_checked)
score       = max(0, share - js_penalty)
```

Crawlers your policy blocks are excluded from the denominator. Deliberately
blocking a training crawler is a choice you made, not a failure, and scoring it
as one would punish you for configuring the tool correctly.

The JavaScript penalty exists because most AI crawlers read the first HTML
response and do not run scripts. A page whose main content is assembled in the
browser is effectively empty to them, whatever robots.txt says.

## What the numbers cannot tell you

A fetch test sends a crawler's user-agent string and reads the reply. A 200 means
robots rules and user-agent filtering did not block the request. It does not
prove the real crawler gets through, because some operators verify crawler IP
ranges. Only bot-hit logs confirm that, which is why module K exists.

When no fetch test reaches the site, crawlers are judged on robots.txt alone and
the score prints a line saying so. A measurement that quietly substitutes a
weaker measurement is worse than one that admits the gap.

## Tuning

These weights are a first pass. They get adjusted against real sites once there
is enough history to see whether the scores move when something real changes and
stay still when nothing does. Any change to a weight belongs in this file, in the
same commit, with the reason.

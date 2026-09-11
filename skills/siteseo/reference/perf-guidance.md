# Performance and Core Web Vitals guidance

last_verified: 2026-09-11

Source: `vendor/web-quality-skills/`, from `addyosmani/web-quality-skills` (MIT),
pinned in `upstream.lock`. Read the vendored files directly when judging a
specific metric. This page is the short version plus the rules siteseo applies
on top.

## Thresholds

Measured at the 75th percentile. Three quarters of visits must be in the good
band.

| Metric | Measures | Good | Needs work | Poor |
| --- | --- | --- | --- | --- |
| Largest Contentful Paint | loading | 2.5 s or less | 2.5 s to 4 s | over 4 s |
| Interaction to Next Paint | interactivity | 200 ms or less | 200 ms to 500 ms | over 500 ms |
| Cumulative Layout Shift | visual stability | 0.1 or less | 0.1 to 0.25 | over 0.25 |

## Field data beats lab data, and siteseo says which it used

Chrome UX Report field data records what real visitors experienced. A Lighthouse
run records what one simulated device experienced once. Presenting the second as
the first is the most common way performance reporting misleads.

Most small sites have no field data at all, because the report needs enough
traffic to anonymise. When that happens siteseo emits `perf.no_field_data` as a
notice and labels every number as a laboratory measurement. It does not silently
fall back and present lab numbers as user experience.

Interaction to Next Paint cannot be measured in a laboratory run at all. It only
appears when the origin has field data, so siteseo never reports a lab INP.

## What to look at first, by metric

**Largest Contentful Paint.** Usually a hero image, a large text block, or a
background image. Check server response time first, since anything over 800 ms
caps how fast the rest can be. Then render-blocking stylesheets and scripts in
the head. Then whether the LCP image is discoverable in the initial HTML rather
than injected by script. Never lazy-load the LCP image: siteseo's
`image.no_lazy_loading` check deliberately skips the first image on a page for
this reason.

**Interaction to Next Paint.** Long tasks blocking the main thread. Break up work
that runs on interaction, and move what does not need the main thread off it.

**Cumulative Layout Shift.** Reserve space before content arrives. Images and
embeds need width and height attributes, which is what `image.dimensions_missing`
checks, and late-loading elements need a placeholder of the right size.

## Claims to avoid making

Do not claim a field improvement right after a fix. Field data needs new visits
to accumulate, so the correct statement is that the lab measurement improved and
the field number should be re-checked in a few weeks.

Do not claim a metric is failing from source code alone. Without a runtime
measurement you can identify likely causes, and saying more than that is a guess
wearing a number.

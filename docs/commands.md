[Docs home](README.md) / Commands

# Commands

| Command | What it does |
| --- | --- |
| `/siteseo` | Guided start: setup, config, first full report, then what to work on. |
| `/siteseo status` | Where this repository stands and what comes next. |
| `/siteseo audit [url]` | Full audit. Build output by default, a live URL when given. |
| `/siteseo page <url>` | Every module against one page. |
| `/siteseo ai` | Module E only. Prints the crawler matrix. |
| `/siteseo agents` | Module O only. Agent readiness level and checks. |
| `/siteseo markdown` | Markdown copy of every page, and the host rule that serves it. |
| `/siteseo pull` | Search Console and Bing into dated history. |
| `/siteseo track` | Run the AI visibility prompt set, after a cost estimate. |
| `/siteseo research <term>` | Paid keyword research, after a cost estimate. |
| `/siteseo fix [ids]` | Propose diffs for autofixable findings. |
| `/siteseo report` | Latest snapshot and the diff against the previous one. Add `--pdf` for a PDF copy. |
| `/siteseo indexnow` | Push changed URLs to every IndexNow engine, Bing among them. |
| `/siteseo gate` | Pre-deploy gate. No model calls, no paid APIs. |
| `/siteseo setup` | Build or refresh the isolated Python environment. |
| `/siteseo doctor` | Runtime, secrets and reference staleness on this machine. |
| `/siteseo sync` | Check upstream and reference drift. |

Every script also runs standalone, without Claude, which is what makes the gate
usable in continuous integration:

```
"${CLAUDE_PLUGIN_ROOT}/scripts/siteseo" run gate.py
```

---

Previous: [Your first report](first-report.md) | Next: [Configuration](configuration.md)

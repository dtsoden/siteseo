[Docs home](README.md) / Commands

# Commands

| Command | What it does |
| --- | --- |
| `/siteseoai` | Guided start: setup, config, first full report, then what to work on. |
| `/siteseoai status` | Where this repository stands and what comes next. |
| `/siteseoai audit [url]` | Full audit. Build output by default, a live URL when given. |
| `/siteseoai page <url>` | Every module against one page. |
| `/siteseoai ai` | Module E only. Prints the crawler matrix. |
| `/siteseoai agents` | Module O only. Agent readiness level and checks. |
| `/siteseoai markdown` | Markdown copy of every page, and the host rule that serves it. |
| `/siteseoai pull` | Search Console and Bing into dated history. |
| `/siteseoai track` | Run the AI visibility prompt set, after a cost estimate. |
| `/siteseoai research <term>` | Paid keyword research, after a cost estimate. |
| `/siteseoai fix [ids]` | Propose diffs for autofixable findings. |
| `/siteseoai report` | Latest snapshot and the diff against the previous one. Add `--pdf` for a PDF copy. |
| `/siteseoai indexnow` | Push changed URLs to every IndexNow engine, Bing among them. |
| `/siteseoai gate` | Pre-deploy gate. No model calls, no paid APIs. |
| `/siteseoai setup` | Build or refresh the isolated Python environment. |
| `/siteseoai doctor` | Runtime, secrets and reference staleness on this machine. |
| `/siteseoai sync` | Check upstream and reference drift. |

Every script also runs standalone, without Claude, which is what makes the gate
usable in continuous integration:

```
"${CLAUDE_PLUGIN_ROOT}/scripts/siteseoai" run gate.py
```

---

Previous: [Your first report](first-report.md) | Next: [Configuration](configuration.md)

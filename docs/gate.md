[Docs home](README.md) / The pre-deploy gate

# The pre-deploy gate

```
/siteseoai gate
```

Modules A, B, C and E against build output. Exits 1 on any error. Warnings and
notices never block. On a small site it finishes in under a second.

It makes no model call and no paid API call, and that is enforced rather than
promised. The run sets an offline flag, and the network source refuses to be
constructed while that flag is set. `tests/test_gate_offline.py` asserts the
refusal actually fires and that the gate still produces a complete result with
the network unavailable.

As a pre-push hook:

```bash
# .git/hooks/pre-push
npm run build && "${CLAUDE_PLUGIN_ROOT}/scripts/siteseoai" run gate.py || exit 1
```

In GitHub Actions:

```yaml
- run: npm run build
- run: "${CLAUDE_PLUGIN_ROOT}/scripts/siteseoai" run gate.py
```

---

Previous: [Findings and fixes](findings-and-fixes.md) | Next: [Markdown for agents](markdown-for-agents.md)

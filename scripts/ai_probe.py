"""Module K: AI visibility.

Asks each configured assistant the same questions several times and records
whether your domain is cited. Answers vary between runs, accounts and locations,
so this never produces a single visibility score. It reports a citation rate with
its sample size, and the change since the last run. A rate without an n is not a
measurement.

The prompt set is your questions from siteseo.yaml plus any grounding queries
imported from Bing AI Performance, since those are real questions that already
retrieved your pages.

Every provider is optional. Missing keys shrink the run rather than failing it,
and the report says which providers were absent.

Every call is metered on the user's own provider account, so a run is paid work
under the same rule as module L: it prints an estimate, waits for --confirm, and
refuses past budget.monthly_usd. Token use varies from run to run, so after the
first run the estimate is the median cost per call of the runs already recorded,
not a guess.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

import dataforseo
import findings as F
import history
import secrets

RUNS_PER_PROMPT = 3
TIMEOUT = 120.0

#: List prices per million tokens and per search or request, used to turn each
#: response's own usage figures into dollars. Verified against each provider's
#: pricing page on the date below.
PRICES_VERIFIED = "2026-10-14"
PRICES = {
    # claude-sonnet-5: $2 / $10 per MTok; web search $10 per 1,000 searches.
    "anthropic": {"input": 2.00, "output": 10.00, "per_search": 0.010},
    # gpt-4.1: $2 / $8 per MTok; web_search tool $10 per 1,000 calls.
    "openai": {"input": 2.00, "output": 8.00, "per_search": 0.010},
    # sonar: $1 / $1 per MTok; request fee $5 per 1,000 at the default low
    # search context.
    "perplexity": {"input": 1.00, "output": 1.00, "per_request": 0.005},
}

#: Per-call placeholder used only until a real run has recorded its cost. Set
#: high on purpose, since search results arrive as input tokens and their size
#: is unknown before the call. Replaced by the median of recorded runs.
FIRST_RUN_ESTIMATE = {"anthropic": 0.15, "openai": 0.10, "perplexity": 0.02}

#: How many recorded runs the median is taken over.
MEDIAN_WINDOW = 10

PROVIDERS = {
    "anthropic": {
        "secret": "SITESEO_ANTHROPIC_API_KEY",
        "model": "claude-sonnet-5",
        "label": "Claude (API, web search on)",
    },
    "openai": {
        "secret": "SITESEO_OPENAI_API_KEY",
        "model": "gpt-4.1",
        "label": "OpenAI (API, web search on)",
    },
    "perplexity": {
        "secret": "SITESEO_PERPLEXITY_API_KEY",
        "model": "sonar",
        "label": "Perplexity Sonar",
    },
}


@dataclass
class Answer:
    provider: str
    model: str
    prompt: str
    run: int
    text: str = ""
    citations: list[str] = field(default_factory=list)
    error: str | None = None
    cost_usd: float = 0.0

    def cites(self, host: str) -> bool:
        if any(host in (urlparse(url).netloc or url) for url in self.citations):
            return True
        return host in self.text

    def names_brand(self, brand: str) -> bool:
        return bool(brand) and brand.lower() in self.text.lower()


def _tokens(price: dict, tokens_in: int, tokens_out: int) -> float:
    return (tokens_in * price["input"] + tokens_out * price["output"]) / 1_000_000


def _ask_anthropic(prompt: str, key: str, model: str) -> Answer:
    answer = Answer("anthropic", model, prompt, 0)
    try:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}],
                "tools": [{"type": "web_search_20250305", "name": "web_search"}],
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        answer.error = secrets.redact(str(exc))
        return answer

    parts: list[str] = []
    for block in data.get("content", []):
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
            for citation in block.get("citations", []) or []:
                if citation.get("url"):
                    answer.citations.append(citation["url"])
        elif block.get("type") == "web_search_tool_result":
            for item in block.get("content", []) or []:
                if isinstance(item, dict) and item.get("url"):
                    answer.citations.append(item["url"])
    answer.text = "\n".join(parts)
    usage = data.get("usage") or {}
    searches = (usage.get("server_tool_use") or {}).get("web_search_requests", 0) or 0
    price = PRICES["anthropic"]
    answer.cost_usd = _tokens(
        price, usage.get("input_tokens", 0) or 0, usage.get("output_tokens", 0) or 0
    ) + searches * price["per_search"]
    return answer


def _ask_openai(prompt: str, key: str, model: str) -> Answer:
    answer = Answer("openai", model, prompt, 0)
    try:
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "input": prompt,
                "tools": [{"type": "web_search"}],
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        answer.error = secrets.redact(str(exc))
        return answer

    parts: list[str] = []
    for item in data.get("output", []) or []:
        for block in item.get("content", []) or []:
            if block.get("type") in {"output_text", "text"}:
                parts.append(block.get("text", ""))
            for annotation in block.get("annotations", []) or []:
                if annotation.get("url"):
                    answer.citations.append(annotation["url"])
    answer.text = "\n".join(parts) or data.get("output_text", "")
    usage = data.get("usage") or {}
    searches = sum(
        1 for item in data.get("output", []) or [] if item.get("type") == "web_search_call"
    )
    price = PRICES["openai"]
    answer.cost_usd = _tokens(
        price, usage.get("input_tokens", 0) or 0, usage.get("output_tokens", 0) or 0
    ) + searches * price["per_search"]
    return answer


def _ask_perplexity(prompt: str, key: str, model: str) -> Answer:
    answer = Answer("perplexity", model, prompt, 0)
    try:
        response = httpx.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        answer.error = secrets.redact(str(exc))
        return answer

    answer.citations = list(data.get("citations") or [])
    choices = data.get("choices") or [{}]
    answer.text = (choices[0].get("message") or {}).get("content", "")
    usage = data.get("usage") or {}
    price = PRICES["perplexity"]
    answer.cost_usd = _tokens(
        price, usage.get("prompt_tokens", 0) or 0, usage.get("completion_tokens", 0) or 0
    ) + price["per_request"]
    return answer


ASK = {"anthropic": _ask_anthropic, "openai": _ask_openai, "perplexity": _ask_perplexity}


def build_prompts(cfg) -> tuple[list[str], list[str]]:
    """Your questions first, then grounding queries already proven to reach you."""
    import bing

    own = list(cfg.prompts)
    grounding = bing.import_ai_performance(cfg).get("grounding_queries", [])
    extra = [q for q in grounding if q not in own]
    return own + extra, extra


def per_call_estimate(cfg, provider: str) -> tuple[float, str]:
    """Median recorded cost per call for this provider, or the placeholder.

    One run says little about the next, because the model searches a different
    number of times and reads different pages each time. The median of the runs
    already paid for is the honest figure; the placeholder is used only until
    one exists, and the message says which was used.
    """
    per_call: list[float] = []
    for path in history.snapshots(cfg, "spend"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if record.get("endpoint") != "ai_probe":
            continue
        row = (record.get("detail") or {}).get(provider) or {}
        if row.get("calls"):
            per_call.append(float(row.get("cost_usd", 0)) / row["calls"])
    per_call = per_call[-MEDIAN_WINDOW:]
    if per_call:
        return statistics.median(per_call), f"median of {len(per_call)} recorded run(s)"
    return FIRST_RUN_ESTIMATE[provider], "first-run placeholder, set high on purpose"


def estimate(cfg, providers: list[str], prompts: int, runs: int) -> tuple[float, list[str]]:
    total = 0.0
    lines: list[str] = []
    for name in providers:
        each, basis = per_call_estimate(cfg, name)
        calls = prompts * runs
        total += each * calls
        lines.append(f"{name}: {calls} calls at ${each:.4f} each ({basis})")
    return total, lines


def run(cfg, *, runs: int = RUNS_PER_PROMPT, limit: int = 0,
        confirmed: bool = False) -> dict:
    host = urlparse(cfg.site).netloc
    brand = host.split(".")[0].replace("-", " ")
    prompts, from_grounding = build_prompts(cfg)
    if limit:
        prompts = prompts[:limit]

    active: dict[str, dict] = {}
    absent: list[str] = []
    for name, spec in PROVIDERS.items():
        key = secrets.get(spec["secret"])
        if key:
            active[name] = {**spec, "key": key}
        else:
            absent.append(f"{spec['label']}: {spec['secret']} is not set")

    if not prompts:
        return {
            "module": "K",
            "available": False,
            "reason": (
                "no prompts to ask. Add questions a real customer would type under "
                "`prompts:` in siteseo.yaml, or import a Bing AI Performance export."
            ),
            "providers_absent": absent,
            "findings": [],
        }
    if not active:
        return {
            "module": "K",
            "available": False,
            "reason": "no AI provider keys are set on this machine",
            "providers_absent": absent,
            "findings": [],
        }

    projected, basis = estimate(cfg, sorted(active), len(prompts), runs)
    allowed, message = dataforseo.budget_check(cfg, projected)
    if not allowed or not confirmed:
        return {
            "module": "K",
            "available": False,
            "needs_confirmation": allowed,
            "estimate_usd": round(projected, 4),
            "estimate_basis": basis,
            "reason": message if not allowed else (
                f"{message}\nRe-run with --confirm to make the calls."
            ),
            "providers_absent": absent,
            "findings": [],
        }

    # The estimate is a median, so a run can cost more. Stop at the cap rather
    # than trusting the estimate to have been right.
    room = cfg.budget.monthly_usd - dataforseo.spend_this_month(cfg)
    spent = 0.0
    spent_by: dict[str, dict] = {name: {"calls": 0, "cost_usd": 0.0} for name in active}
    stopped_at_cap = False
    answers: list[Answer] = []
    for prompt in prompts:
        for name, spec in active.items():
            for index in range(runs):
                if spent >= room:
                    stopped_at_cap = True
                    break
                answer = ASK[name](prompt, spec["key"], spec["model"])
                answer.run = index + 1
                answers.append(answer)
                spent += answer.cost_usd
                spent_by[name]["calls"] += 1
                spent_by[name]["cost_usd"] = round(spent_by[name]["cost_usd"] + answer.cost_usd, 6)

    dataforseo.record_spend(cfg, "ai_probe", spent, detail=spent_by)

    # Citation rate per prompt per provider, always with n.
    tally: dict[tuple[str, str], list[Answer]] = defaultdict(list)
    for answer in answers:
        tally[(answer.prompt, answer.provider)].append(answer)

    rows = []
    competitors = [c.lower() for c in cfg.competitors]
    for (prompt, provider), group in sorted(tally.items()):
        usable = [a for a in group if not a.error]
        cited = sum(1 for a in usable if a.cites(host))
        named = sum(1 for a in usable if a.names_brand(brand))
        competitor_hits: dict[str, int] = defaultdict(int)
        for answer in usable:
            blob = (answer.text + " " + " ".join(answer.citations)).lower()
            for competitor in competitors:
                if competitor in blob:
                    competitor_hits[competitor] += 1
        rows.append(
            {
                "prompt": prompt,
                "provider": provider,
                "model": active[provider]["model"],
                "n": len(usable),
                "errors": len(group) - len(usable),
                "cited": cited,
                "citation_rate": round(cited / len(usable), 3) if usable else None,
                "brand_named": named,
                "competitors_cited": dict(competitor_hits),
                "from_grounding": prompt in from_grounding,
            }
        )

    prior = history.latest(cfg, "ai-visibility")
    emitted = _findings(cfg, rows, prior)

    return {
        "module": "K",
        "kind": "ai-visibility",
        "available": True,
        "site": cfg.site,
        "host": host,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runs_per_prompt": runs,
        "providers": sorted(active),
        "providers_absent": absent,
        "estimate_usd": round(projected, 4),
        "cost_usd": round(spent, 4),
        "cost_by_provider": spent_by,
        "stopped_at_cap": stopped_at_cap,
        "prompts": len(prompts),
        "prompts_from_grounding": len(from_grounding),
        "rows": rows,
        "answers": [
            {
                "provider": a.provider,
                "prompt": a.prompt,
                "run": a.run,
                "cited": a.cites(host),
                "cost_usd": round(a.cost_usd, 6),
                "citations": a.citations[:20],
                "text": a.text[:4000],
                "error": a.error,
            }
            for a in answers
        ],
        "findings": [f.to_dict() for f in emitted],
        "notes": [
            "Answers vary between runs, accounts and locations. Read these as trends "
            "across several runs, never as a single verdict.",
            "No blended AI visibility score is produced, deliberately.",
            f"Cost is computed from each response's usage at list prices verified "
            f"{PRICES_VERIFIED}. The provider's billing page is the final word.",
        ] + (
            ["Stopped early: the monthly budget cap was reached partway through."]
            if stopped_at_cap else []
        ),
    }


def _findings(cfg, rows: list[dict], prior: dict | None) -> list[F.Finding]:
    emitted: list[F.Finding] = []
    previous = {
        (row["prompt"], row["provider"]): row.get("citation_rate")
        for row in (prior or {}).get("rows", [])
    }

    for row in rows:
        if row["citation_rate"] == 0 and row["n"]:
            emitted.append(
                F.make(
                    "ai_vis.not_cited",
                    cfg.site,
                    f'{row["provider"]} did not cite {cfg.site} for "{row["prompt"][:70]}" '
                    f'in {row["n"]} run(s)',
                    group=f'{row["provider"]}|{row["prompt"][:40]}',
                )
            )
        was = previous.get((row["prompt"], row["provider"]))
        now = row["citation_rate"]
        if was is not None and now is not None and now < was:
            emitted.append(
                F.make(
                    "ai_vis.citation_rate_dropped",
                    cfg.site,
                    f'{row["provider"]} citation rate for "{row["prompt"][:60]}" fell from '
                    f'{was:.2f} to {now:.2f} (n={row["n"]})',
                    group=f'{row["provider"]}|{row["prompt"][:40]}',
                )
            )

    return F.order(F.merge(emitted))


def main() -> int:
    import argparse

    import config as config_module

    parser = argparse.ArgumentParser(description="Module K: AI visibility tracking")
    parser.add_argument("--runs", type=int, default=RUNS_PER_PROMPT)
    parser.add_argument("--limit", type=int, default=0, help="cap the number of prompts")
    parser.add_argument("--no-snapshot", action="store_true")
    parser.add_argument("--confirm", action="store_true",
                        help="authorise the paid calls after reading the estimate")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = run(cfg, runs=args.runs, limit=args.limit, confirmed=args.confirm)

    if result["available"] and not args.no_snapshot:
        result["snapshot"] = str(history.write(cfg, "ai-visibility", result))

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    if not result["available"]:
        print(f"AI visibility not run: {result['reason']}")
        for line in result.get("estimate_basis", []):
            print(f"  {line}")
        for line in result.get("providers_absent", []):
            print(f"  {line}")
        return 0

    print(f"AI visibility for {result['host']}")
    print(f"  {result['prompts']} prompts, {result['runs_per_prompt']} runs each, "
          f"providers: {', '.join(result['providers'])}")
    print()
    print(f"{'provider':12s} {'n':>3s} {'cited':>6s} {'rate':>6s}  prompt")
    for row in result["rows"]:
        rate = "n/a" if row["citation_rate"] is None else f"{row['citation_rate']:.2f}"
        print(f"{row['provider']:12s} {row['n']:3d} {row['cited']:6d} {rate:>6s}  "
              f"{row['prompt'][:50]}")
    print()
    print(f"  cost ${result['cost_usd']:.4f} (estimated ${result['estimate_usd']:.4f})")
    for line in result.get("providers_absent", []):
        print(f"  not run: {line}")
    for note in result["notes"]:
        print(f"  Note: {note}")
    if "snapshot" in result:
        print(f"\nSnapshot: {result['snapshot']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

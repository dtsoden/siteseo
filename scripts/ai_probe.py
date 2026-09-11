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
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

import findings as F
import history
import secrets

RUNS_PER_PROMPT = 3
TIMEOUT = 120.0

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

    def cites(self, host: str) -> bool:
        if any(host in (urlparse(url).netloc or url) for url in self.citations):
            return True
        return host in self.text

    def names_brand(self, brand: str) -> bool:
        return bool(brand) and brand.lower() in self.text.lower()


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
    return answer


ASK = {"anthropic": _ask_anthropic, "openai": _ask_openai, "perplexity": _ask_perplexity}


def build_prompts(cfg) -> tuple[list[str], list[str]]:
    """Your questions first, then grounding queries already proven to reach you."""
    import bing

    own = list(cfg.prompts)
    grounding = bing.import_ai_performance(cfg).get("grounding_queries", [])
    extra = [q for q in grounding if q not in own]
    return own + extra, extra


def run(cfg, *, runs: int = RUNS_PER_PROMPT, limit: int = 0) -> dict:
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

    answers: list[Answer] = []
    for prompt in prompts:
        for name, spec in active.items():
            for index in range(runs):
                answer = ASK[name](prompt, spec["key"], spec["model"])
                answer.run = index + 1
                answers.append(answer)

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
        "prompts": len(prompts),
        "prompts_from_grounding": len(from_grounding),
        "rows": rows,
        "answers": [
            {
                "provider": a.provider,
                "prompt": a.prompt,
                "run": a.run,
                "cited": a.cites(host),
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
        ],
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
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        cfg = config_module.load()
    except config_module.ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = run(cfg, runs=args.runs, limit=args.limit)

    if result["available"] and not args.no_snapshot:
        result["snapshot"] = str(history.write(cfg, "ai-visibility", result))

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    if not result["available"]:
        print(f"AI visibility unavailable: {result['reason']}")
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
    for line in result.get("providers_absent", []):
        print(f"  not run: {line}")
    for note in result["notes"]:
        print(f"  Note: {note}")
    if "snapshot" in result:
        print(f"\nSnapshot: {result['snapshot']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

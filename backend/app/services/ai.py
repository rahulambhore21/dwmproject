"""AI interpretation layer.

Deterministic analytics produce evidence; the interpreter may only restate it.
- Default: deterministic interpreter (no network, no key needed).
- Optional: Claude (set ANTHROPIC_API_KEY). Output is validated against the evidence;
  any invented number, unknown evidence id or causal claim triggers a fallback to the
  deterministic reading, and the response says so.
"""
from __future__ import annotations

import json
import logging
import re

from ..config import get_settings

log = logging.getLogger("signal.ai")

CAUSAL = re.compile(r"\b(causes?|caused|because of|due to|proves?|proven|guarantees?|will (?:increase|improve|boost|drive)|definitely|certainly)\b", re.I)
NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?")
EVID_ID = re.compile(r"\bE\d+\b")

SYSTEM = """You are the interpretation layer of SIGNAL, a content analytics product.
You receive EVIDENCE produced by deterministic analytics. Write 3 to 6 short findings that restate and connect that evidence for a content team.

Rules (strict):
- Use ONLY numbers that appear in the evidence text. Never compute new numbers, never round differently, never invent sample sizes.
- Every finding must cite the evidence ids it relies on.
- Historical patterns are associations. Never claim causation, never promise outcomes. Use hedged language ("is associated with", "suggests", "may").
- If evidence is thin (small n, wide ranges, non-significant), say so plainly.
- Do not give advice that the evidence does not support.
Return JSON only, no prose, in this shape:
{"statements":[{"text":"...","evidence_ids":["E1"],"strength":"weak|moderate|strong"}],"caveats":["..."]}"""


def _allowed_numbers(evidence: list[dict]) -> set[float]:
    allowed: set[float] = set()
    for e in evidence:
        for x in e.get("numbers", []):
            allowed.add(round(float(x), 4))
        for m in NUMBER.findall(e.get("text", "")):
            allowed.add(round(float(m), 4))
    return allowed


def _matches(v: float, allowed: set[float]) -> bool:
    for a in allowed:
        for cand in (abs(a), abs(a) * 100, abs(a) / 100):  # same quantity as a fraction or a percentage
            if abs(abs(v) - cand) <= max(0.051, abs(cand) * 0.005):
                return True
    return False


def validate(statements: list[dict], evidence: list[dict]) -> str | None:
    """Return None if valid, else the reason."""
    ids = {e["id"] for e in evidence}
    allowed = _allowed_numbers(evidence)
    if not statements:
        return "no statements"
    for s in statements:
        text = str(s.get("text", ""))
        cited = s.get("evidence_ids") or []
        if not cited or any(c not in ids for c in cited):
            return f"unknown or missing evidence ids in: {text[:60]}"
        if CAUSAL.search(text):
            return f"causal or promissory language in: {text[:60]}"
        for m in NUMBER.findall(EVID_ID.sub("", text)):
            if not _matches(float(m), allowed):
                return f"number {m} not found in evidence"
    return None


def _llm(evidence: list[dict], scope: str) -> dict | None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=45.0, max_retries=1)
    payload = json.dumps({"scope": scope, "evidence": [{k: e[k] for k in ("id", "label", "text", "n")} for e in evidence]}, ensure_ascii=False)
    resp = client.messages.create(
        model=settings.anthropic_model, max_tokens=4000, system=SYSTEM,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": payload}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("model declined the request")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    return json.loads(text)


def interpret(scope: str, evidence: list[dict], statements: list[dict]) -> dict:
    base = {"scope": scope, "evidence": evidence, "disclaimer":
            "Generated from deterministic analytics. Patterns are historical associations, not proven causes."}
    if not evidence:
        return {**base, "source": "deterministic", "statements": [], "caveats": ["Not enough data to interpret."], "fallback_reason": None}
    fallback_reason = None
    if get_settings().anthropic_api_key:
        try:
            out = _llm(evidence, scope)
            problem = validate(out.get("statements", []), evidence) if out else "empty response"
            if out and problem is None:
                strengths = {"weak", "moderate", "strong"}
                stm = [{"text": s["text"], "evidence_ids": s["evidence_ids"], "strength": s.get("strength") if s.get("strength") in strengths else "moderate"}
                       for s in out["statements"]]
                return {**base, "source": "llm", "model": get_settings().anthropic_model, "statements": stm,
                        "caveats": [str(c) for c in out.get("caveats", [])][:4], "fallback_reason": None}
            fallback_reason = f"LLM output rejected by evidence validator ({problem})"
        except Exception as exc:  # network, auth, parse: never break the product
            log.warning("LLM interpretation failed: %s", exc)
            fallback_reason = f"LLM unavailable ({type(exc).__name__})"
    caveats = ["Based on historical associations in this workspace; not causal proof."]
    if any(e.get("n") is not None and e["n"] < 15 for e in evidence):
        caveats.append("Some evidence rests on fewer than 15 posts.")
    return {**base, "source": "deterministic", "statements": statements, "caveats": caveats, "fallback_reason": fallback_reason}

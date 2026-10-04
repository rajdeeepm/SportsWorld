"""Conversational rewrite of the analyst's answer, with a number-faithfulness check.

The self-hosted Llama turns the engine's structured answer into a few natural sentences. Every number in the
rewrite must appear in the engine's answer (percentages, records, dates, wins); otherwise the rewrite is discarded
and the structured answer is shown. The model never computes or invents a figure.
"""
from __future__ import annotations

import re

import httpx

from sportsworld.config import get_settings

SYSTEM = (
    "You are SportsWorld's on-air analyst. Rewrite the DATA into 2-4 natural, confident sentences that answer the "
    "user's QUESTION first. Use only facts and numbers that appear in DATA, written exactly as in DATA (keep the % "
    "signs and decimals). Do not add numbers, odds, players, history or opinions that are not in DATA. No lists, "
    "no markdown, no links. Describe how competitive a game is only with the label DATA gives it (toss-up, lean, "
    "clear favourite, one-sided); never call a game close, tight or a coin flip unless DATA labels it a toss-up."
)

NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)")


def _numbers(text: str) -> set[str]:
    return {n.rstrip("0").rstrip(".") if "." in n else n for n in NUM.findall(text.replace(",", ""))}


CLOSE = re.compile(r"\b(close|closely|tight|toss[- ]?up|coin[- ]?flip|nail[- ]?biter|evenly matched|even matchup|neck and neck|down to the wire|could go either way)\b", re.I)


JUDGEMENT = re.compile(r"\b(favou?rites?|underdogs?|competitive|dominan\w*|upsets?|blowouts?|lopsided|must[- ]win|lock)\b", re.I)


def faithful(prose: str, source: str) -> bool:
    """Every number must come from the engine's answer, and a game may only be called close if the engine says so."""
    allowed = _numbers(source) | {str(i) for i in range(0, 11)}  # small counts ("two games") are fine
    if CLOSE.search(prose) and not re.search(r"toss-up|coin flip", source, re.I):
        return False
    for w in JUDGEMENT.findall(prose):  # no verdicts the engine did not give ("clear favourite", "upset", ...)
        if not re.search(re.escape(w[:6]), source, re.I):
            return False
    return _numbers(prose) <= allowed


def rewrite(question: str, structured: str) -> str | None:
    s = get_settings()
    if not s.llm_base_url or s.llm_provider == "deterministic":
        return None
    data = re.sub(r"https?://\S+|`[^`]*`", "", structured).replace("**", "").replace("*", "")
    body = {"model": s.llm_model, "temperature": 0, "max_tokens": 220,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"QUESTION: {question}\n\nDATA:\n{data}"}]}
    try:
        r = httpx.post(f"{s.llm_base_url.rstrip('/')}/chat/completions", json=body,
                       headers={"Authorization": f"Bearer {s.llm_api_key or 'none'}"}, timeout=45)
        r.raise_for_status()
        prose = r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
    return prose if prose and faithful(prose, data) else None

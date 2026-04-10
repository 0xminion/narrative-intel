"""Sentiment analysis using batched LLM calls. 5-class: extreme pos/slight pos/neutral/slight neg/extreme neg."""

import json
import logging
import requests
from typing import Any

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a crypto social sentiment analyzer. You will receive mentions grouped by narrative. 
For each narrative, classify EVERY mention into exactly one of 5 categories:
- EXTREME_POSITIVE: euphoric, heavy conviction, "best setup this cycle", accumulation calls with urgency
- SLIGHT_POSITIVE: cautiously bullish, interest, "keeping an eye on", moderate shilling
- NEUTRAL: factual reporting without opinion, balanced debate, neither bullish nor bearish
- SLIGHT_NEGATIVE: cautious, "overvalued", taking profits, skeptical but not hostile
- EXTREME_NEGATIVE: "scam", "rug", "dead project", panic selling, hostile criticism

Do NOT default to neutral. If there is ANY lean positive or negative, classify accordingly. 
Only use neutral when the mention is genuinely purely factual with zero opinion.

For each narrative return a JSON object with this exact structure:
{
  "narrative_name": {
    "counts": {"extreme_positive": N, "slight_positive": N, "neutral": N, "slight_negative": N, "extreme_negative": N},
    "score": calculated_score_from_-100_to_+100,
    "label": "one of: EXTREME BULLISH/SLIGHT BULLISH/MIXED/SLIGHT BEARISH/EXTREME BEARISH",
    "positive_reasons": ["specific reason 1 with evidence from text", "reason 2", "reason 3"],
    "negative_reasons": ["specific reason 1 with evidence from text", "reason 2", "reason 3"]
  }
}

Score formula: ((extreme_positive*2 + slight_positive*1) - (slight_negative*1 + extreme_negative*2)) / (total_mentions * 2) * 100

Label thresholds:
  +70 to +100 = EXTREME BULLISH
  +30 to +69  = SLIGHT BULLISH
  -29 to +29  = MIXED
  -30 to -69  = SLIGHT BEARISH
  -70 to -100 = EXTREME BEARISH

Return ONLY valid JSON. No markdown, no explanation."""


def analyze_sentiment(narrative_mentions: dict[str, list[dict]], provider: str,
                      model: str, api_key: str) -> dict:
    """Batched sentiment analysis across all narratives. One LLM call.

    Args:
        narrative_mentions: { "narrative_name": [mention_dicts with 'text' and 'engagement'] }
        provider: "openai" or "anthropic"
        model: model name
        api_key: LLM API key

    Returns:
        { "narrative_name": { "score": int, "label": str, "counts": {}, "positive_reasons": [], "negative_reasons": [] } }
    """
    # Build the input payload
    payload = {}
    for narrative, mentions in narrative_mentions.items():
        payload[narrative] = [
            {"text": m["text"][:300], "engagement": m["engagement"]}
            for m in mentions[:30]  # top 30 by engagement
        ]

    user_msg = f"Analyze sentiment for these narrative mentions:\n\n{json.dumps(payload, indent=2)}"

    try:
        raw_response = _call_llm(provider, model, api_key, SYSTEM_PROMPT, user_msg)
        # Clean response - remove markdown fences if present
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

        result = json.loads(cleaned)
        log.info(f"Sentiment analysis complete for {len(result)} narratives")
        return result
    except json.JSONDecodeError as e:
        log.error(f"Failed to parse LLM sentiment response: {e}")
        log.debug(f"Raw response: {raw_response[:500]}")
        return _fallback_sentiment(narrative_mentions)
    except Exception as e:
        log.error(f"Sentiment analysis failed: {e}")
        return _fallback_sentiment(narrative_mentions)


def _call_llm(provider: str, model: str, api_key: str, system: str, user: str) -> str:
    """Call the appropriate LLM API."""
    if provider == "openai":
        return _call_openai(model, api_key, system, user)
    elif provider == "anthropic":
        return _call_anthropic(model, api_key, system, user)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def _call_openai(model: str, api_key: str, system: str, user: str) -> str:
    """Call OpenAI API."""
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.1,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_anthropic(model: str, api_key: str, system: str, user: str) -> str:
    """Call Anthropic API."""
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "temperature": 0.1,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def _fallback_sentiment(narrative_mentions: dict) -> dict:
    """Fallback sentiment using engagement-based heuristic if LLM fails."""
    result = {}
    for narrative, mentions in narrative_mentions.items():
        if not mentions:
            result[narrative] = {"score": 0, "label": "MIXED", "counts": {},
                                  "positive_reasons": [], "negative_reasons": ["No data available"]}
            continue
        smart_count = sum(1 for m in mentions if m.get("is_smart"))
        total = len(mentions)
        smart_ratio = smart_count / total if total else 0
        score = int((smart_ratio - 0.3) * 100)  # Rough heuristic
        score = max(-100, min(100, score))
        result[narrative] = {
            "score": score,
            "label": "MIXED",
            "counts": {"unknown": total},
            "positive_reasons": [f"{smart_count} smart account mentions detected"],
            "negative_reasons": [f"LLM analysis unavailable, using heuristic"],
        }
    return result

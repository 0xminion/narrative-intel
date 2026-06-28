"""Question generation from data contradictions. Programmatic detection + LLM polish."""

import json
import logging
import requests
from typing import Any

log = logging.getLogger(__name__)


def detect_contradictions(narratives: list[dict], shifts: dict, classified: dict,
                          sentiment: dict) -> list[dict]:
    """Detect data contradictions programmatically. Returns list of contradiction objects."""
    contradictions = []

    for shift_type in ["positive", "negative", "neutral"]:
        for entry in shifts.get(shift_type, []):
            name = entry["name"]
            name_lower = name.lower()

            # Get tokens for this narrative
            narrative_tokens = {s: info for s, info in classified.items()
                                if (info.get("narrative") or "").lower() == name_lower}

            # Contradiction 1: social_up_price_flat
            if shift_type == "positive" and narrative_tokens:
                max_change = max((t.get("price_data", {}).get("change_24h", 0) or 0)
                                 for t in narrative_tokens.values())
                if max_change < 5:
                    contradictions.append({
                        "type": "social_up_price_flat",
                        "narrative": name,
                        "evidence": f"Rank improved ({entry.get('delta_display', '')}) but top tokens show <5% price movement",
                        "tokens": list(narrative_tokens.keys())[:3],
                    })

            # Contradiction 2: price_up_social_flat
            if shift_type in ("negative", "neutral") and narrative_tokens:
                max_change = max((t.get("price_data", {}).get("change_24h", 0) or 0)
                                 for t in narrative_tokens.values())
                if max_change > 15:
                    contradictions.append({
                        "type": "price_up_social_flat",
                        "narrative": name,
                        "evidence": f"Tokens up {max_change:.0f}% but narrative rank {'dropped' if shift_type == 'negative' else 'unchanged'}",
                        "tokens": list(narrative_tokens.keys())[:3],
                    })

            # Contradiction 3: volume_concentration
            if narrative_tokens:
                volumes = {s: (t.get("price_data", {}).get("volume", 0) or 0)
                           for s, t in narrative_tokens.items()}
                total_vol = sum(volumes.values())
                if total_vol > 0:
                    max_vol_token = max(volumes, key=volumes.get)
                    max_vol_pct = volumes[max_vol_token] / total_vol * 100
                    if max_vol_pct > 60:
                        contradictions.append({
                            "type": "volume_concentration",
                            "narrative": name,
                            "evidence": f"${max_vol_token} has {max_vol_pct:.0f}% of narrative's total volume",
                            "tokens": [max_vol_token],
                        })

            # Contradiction 4: signal_stuck
            for symbol, info in narrative_tokens.items():
                history = info.get("signal_history", [])
                if len(history) >= 3 and all(h == "social-first" for h in history[-3:]):
                    contradictions.append({
                        "type": "signal_stuck",
                        "narrative": name,
                        "evidence": f"${symbol} stuck at 'social-first' for {len(history)} days with no price follow-through",
                        "tokens": [symbol],
                    })

            # Contradiction 5: sentiment_mismatch
            sent = sentiment.get(name, {})
            sent_score = sent.get("score", 0)
            if shift_type == "positive" and sent_score < -20:
                contradictions.append({
                    "type": "sentiment_mismatch",
                    "narrative": name,
                    "evidence": f"Rank improving but sentiment is {sent.get('label', 'unknown')} ({sent_score})",
                    "tokens": list(narrative_tokens.keys())[:3],
                })
            elif shift_type == "negative" and sent_score > 20:
                contradictions.append({
                    "type": "sentiment_mismatch",
                    "narrative": name,
                    "evidence": f"Rank dropping but sentiment is {sent.get('label', 'unknown')} ({sent_score})",
                    "tokens": list(narrative_tokens.keys())[:3],
                })

    return contradictions


def generate_questions(contradictions: list[dict], narratives_with_data: dict,
                       provider: str, model: str, api_key: str,
                       base_url: str = "") -> dict:
    """Generate per-narrative 'think about' questions from contradictions.
    Programmatic templates + LLM polish.

    Returns: { "narrative_name": ["question 1", "question 2", ...] }
    """
    # Group contradictions by narrative
    by_narrative = {}
    for c in contradictions:
        name = c["narrative"]
        if name not in by_narrative:
            by_narrative[name] = []
        by_narrative[name].append(c)

    if not by_narrative:
        return {}

    # Build template questions from contradictions
    template_questions = {}
    for name, cons in by_narrative.items():
        questions = []
        for c in cons:
            q = _template_question(c, narratives_with_data.get(name, {}))
            if q:
                questions.append(q)
        template_questions[name] = questions

    # Polish with LLM
    try:
        polished = _llm_polish_questions(template_questions, provider, model, api_key, base_url)
        return polished
    except Exception as e:
        log.warning(f"LLM polish failed, using templates: {e}")
        return template_questions


def generate_weekly_questions(reports: list[str], agg: dict, token_progression: dict,
                              provider: str, model: str, api_key: str,
                              base_url: str = "") -> list[str]:
    """Generate weekly 'questions to research' section."""
    prompt = f"""Based on this weekly narrative data, generate 4-6 deep research questions.

Narrative movements this week: {json.dumps(agg.get('summary', {}), default=str, indent=2)}
Token signal progressions: {json.dumps(token_progression, default=str, indent=2)}

Rules:
- Questions must reference SPECIFIC data points from above
- Questions should be investigative, not obvious
- Each question should suggest WHERE to look for answers
- Include both sector-level and token-level questions
- Focus on contradictions and patterns, not surface observations

Return as JSON array: ["question 1", "question 2", ...]"""

    try:
        raw = _call_llm(provider, model, api_key,
                        "You are a crypto research analyst generating deep investigative questions.",
                        prompt, base_url)
        return json.loads(_clean_json_response(raw))
    except Exception as e:
        log.warning(f"Weekly question generation failed: {e}")
        return ["Review this week's narrative shifts for patterns worth investigating further."]


def _template_question(contradiction: dict, context: dict) -> str | None:
    """Generate a question from a contradiction type + evidence."""
    c_type = contradiction["type"]
    evidence = contradiction["evidence"]
    tokens = contradiction.get("tokens", [])
    token_str = ", ".join(f"${t}" for t in tokens) if tokens else "key tokens"

    templates = {
        "social_up_price_flat": (
            f"{evidence}. Is this narrative building before capital flows in, "
            f"or is it social noise without real market conviction? "
            f"Check on-chain volume for {token_str} to distinguish."
        ),
        "price_up_social_flat": (
            f"{evidence}. If CT hasn't caught up, who's buying? "
            f"Is this institutional/whale accumulation that retail will chase later, "
            f"or a short-lived pump? Check {token_str} holder distribution."
        ),
        "volume_concentration": (
            f"{evidence}. Is this a single whale or coordinated group driving the narrative? "
            f"If volume is concentrated, the narrative is fragile — one exit kills momentum. "
            f"Check {token_str} trade size distribution."
        ),
        "signal_stuck": (
            f"{evidence}. Social conviction exists but price hasn't validated. "
            f"Either this is accumulation phase (bullish) or a dead narrative (bearish). "
            f"Check {token_str} dev activity and upcoming catalysts."
        ),
        "sentiment_mismatch": (
            f"{evidence}. The crowd sentiment contradicts the price action. "
            f"This usually means one is about to revert. "
            f"Track {token_str} over the next 24h to see which side wins."
        ),
    }
    return templates.get(c_type)


def _llm_polish_questions(template_questions: dict, provider: str, model: str,
                          api_key: str, base_url: str = "") -> dict:
    """Polish template questions with LLM for natural phrasing."""
    prompt = f"""Polish these data-grounded crypto questions. Keep all facts and numbers EXACTLY as given.
Do NOT add new claims or data. Only improve phrasing and flow.

Input:
{json.dumps(template_questions, indent=2)}

Return the same JSON structure with polished text. Keep each question as a single cohesive thought."""

    raw = _call_llm(provider, model, api_key,
                    "You are a text editor. Polish questions without changing any facts.",
                    prompt, base_url)
    return json.loads(_clean_json_response(raw))


def _clean_json_response(raw: str) -> str:
    """Strip markdown code fences and json prefix from LLM response."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()
    return cleaned


def _call_llm(provider: str, model: str, api_key: str, system: str, user: str,
              base_url: str = "") -> str:
    """Call the appropriate LLM API."""
    default_urls = {
        "openai": "https://api.openai.com/v1",
        "openrouter": "https://openrouter.ai/api/v1",
    }

    if provider in ("openai", "openrouter"):
        url = base_url if base_url else default_urls.get(provider, default_urls["openai"])
        url = f"{url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/narrative-intel"
        resp = requests.post(url, headers=headers, json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
        }, timeout=90)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    elif provider == "anthropic":
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                      "Content-Type": "application/json"},
            json={"model": model, "max_tokens": 4096, "system": system,
                  "messages": [{"role": "user", "content": user}], "temperature": 0.3},
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]
    else:
        raise ValueError(f"Unknown provider: {provider}")


def generate_weekly_themes(reports: list[str], agg: dict,
                           provider: str, model: str, api_key: str,
                           base_url: str = "") -> dict:
    """Generate weekly biggest themes (positive + negative) from daily reports."""
    prompt = f"""Based on this week's daily narrative reports, identify the BIGGEST THEMES.

Aggregated narrative movements: {json.dumps(agg.get('summary', {}), default=str, indent=2)}

For each major theme:
1. What happened (synthesis from the data)
2. Why it matters
3. Key moments/days

Identify:
- Top 2-3 POSITIVE themes (narratives that gained momentum)
- Top 1-2 NEGATIVE themes (narratives that lost momentum)

Return JSON:
{{
  "positive": [
    {{"theme": "name", "what_happened": "synthesis", "why_it_matters": "analysis", "key_moments": ["mon: x", "wed: y"]}},
  ],
  "negative": [
    {{"theme": "name", "what_happened": "synthesis", "why_it_matters": "analysis", "key_moments": ["tue: x"]}},
  ]
}}"""

    try:
        raw = _call_llm(provider, model, api_key,
                        "You are a crypto narrative analyst. Synthesize themes from data.",
                        prompt, base_url)
        return json.loads(_clean_json_response(raw))
    except Exception as e:
        log.warning(f"Weekly themes generation failed: {e}")
        return {"positive": [], "negative": []}

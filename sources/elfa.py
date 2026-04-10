"""Elfa API v2 client. All social intelligence data comes from here."""

import requests
import logging
import time
from typing import Any

log = logging.getLogger(__name__)

BASE = "https://api.elfa.ai/v2"


def _headers(api_key: str) -> dict:
    return {
        "x-elfa-api-key": api_key,
        "Accept": "application/json",
    }


def _get(api_key: str, path: str, params: dict | None = None, retries: int = 3) -> dict:
    """GET request with retry on transient failures."""
    url = f"{BASE}{path}"
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=_headers(api_key), params=params, timeout=30)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                log.warning(f"Rate limited, waiting {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt < retries - 1:
                wait = 2 ** attempt
                log.warning(f"Request failed ({e}), retrying in {wait}s...")
                time.sleep(wait)
            else:
                log.error(f"Request failed after {retries} attempts: {e}")
                raise


def get_trending_narratives(api_key: str, time_frame: str = "day", max_narratives: int = 10) -> list[dict]:
    """Fetch trending narratives. Costs 5 credits."""
    data = _get(api_key, "/data/trending-narratives", {
        "timeFrame": time_frame,
        "maxNarratives": max_narratives,
        "maxTweetsPerNarrative": 5,
    })
    results = []
    raw = data.get("data", data)
    if isinstance(raw, dict):
        raw = [raw]
    for item in raw:
        name = item.get("name") or item.get("narrative") or item.get("title", "Unknown")
        keywords = item.get("keywords", [])
        if not keywords:
            # Generate keywords from narrative name
            keywords = [name.lower()] + name.lower().split()[:3]
        results.append({
            "name": name,
            "keywords": keywords if isinstance(keywords, list) else [str(keywords)],
            "rank": item.get("rank", len(results) + 1),
            "tweet_count": item.get("tweetCount", item.get("count", 0)),
        })
    # Ensure ranks
    for i, r in enumerate(results):
        if not r.get("rank"):
            r["rank"] = i + 1
    return results


def get_keyword_mentions(api_key: str, keywords: list[str], time_window: str = "24h",
                         limit: int = 30, search_type: str = "or") -> list[dict]:
    """Search mentions by keywords. Costs 1 credit per call."""
    kw_str = ",".join(keywords[:5])  # API max 5 keywords
    data = _get(api_key, "/data/keyword-mentions", {
        "keywords": kw_str,
        "timeWindow": time_window,
        "limit": limit,
        "searchType": search_type,
    })
    results = []
    for item in data.get("data", []):
        results.append({
            "text": item.get("content", item.get("text", "")),
            "engagement": item.get("engagement", item.get("likeCount", 0)) or 0,
            "account": item.get("username", item.get("account", "")),
            "is_smart": item.get("isSmartAccount", item.get("smartAccount", False)),
            "token": item.get("token", item.get("cashtag", "")),
            "timestamp": item.get("timestamp", item.get("createdAt", "")),
        })
    # Sort by engagement descending
    results.sort(key=lambda x: x["engagement"], reverse=True)
    return results


def get_trending_tokens(api_key: str, time_window: str = "4h",
                        min_mentions: int = 15, page_size: int = 50) -> list[dict]:
    """Get tokens with rapid social velocity. Costs 1 credit."""
    data = _get(api_key, "/aggregations/trending-tokens", {
        "timeWindow": time_window,
        "minMentions": min_mentions,
        "pageSize": page_size,
    })
    results = []
    raw = data.get("data", data)
    if isinstance(raw, dict):
        raw = raw.get("tokens", raw.get("items", [raw]))
    for item in raw:
        results.append({
            "token": item.get("token", item.get("symbol", item.get("name", ""))),
            "mentions": item.get("mentionCount", item.get("mentions", 0)) or 0,
            "engagement": item.get("engagement", 0) or 0,
        })
    return results

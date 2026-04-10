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
            resp = requests.get(url, headers=_headers(api_key), params=params, timeout=60)
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
    # Handle nested: data.trending_narratives, data.narratives, data.items
    if isinstance(raw, dict):
        raw = raw.get("trending_narratives", raw.get("narratives", raw.get("items", [raw])))
    if isinstance(raw, dict):
        raw = [raw]

    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        name = item.get("narrative") or item.get("name") or item.get("title", f"Narrative {i+1}")
        keywords = item.get("keywords", [])
        if not keywords:
            words = name.lower().split()
            stops = {"the", "a", "an", "is", "at", "on", "in", "of", "to", "for", "and", "or",
                     "vs", "with", "without", "from", "its", "his", "her", "our", "their"}
            keywords = [w for w in words if w not in stops and len(w) > 2][:5]
            if not keywords:
                keywords = [name.lower()[:30]]
        results.append({
            "name": name,
            "keywords": keywords,
            "rank": i + 1,
            "tweet_count": item.get("tweetCount", len(item.get("tweet_ids", []))),
            "source_links": item.get("source_links", []),
        })

    return results


def get_keyword_mentions(api_key: str, keywords: list[str], time_window: str = "24h",
                         limit: int = 30, search_type: str = "or") -> list[dict]:
    """Search mentions by keywords. Costs 1 credit per call.
    Note: Returns metadata only (engagement, account), not tweet text.
    """
    kw_str = ",".join(keywords[:5])  # API max 5 keywords
    data = _get(api_key, "/data/keyword-mentions", {
        "keywords": kw_str,
        "timeWindow": time_window,
        "limit": limit,
        "searchType": search_type,
    })
    results = []
    raw = data.get("data", data)
    if isinstance(raw, dict):
        raw = raw.get("items", raw.get("mentions", [raw]))

    for item in raw:
        if not isinstance(item, dict):
            continue
        account = item.get("account", {})
        engagement = item.get("likeCount", 0) + item.get("repostCount", 0) * 2 + item.get("viewCount", 0) // 100
        results.append({
            "tweet_id": item.get("tweetId", ""),
            "link": item.get("link", ""),
            "engagement": engagement,
            "likes": item.get("likeCount", 0),
            "reposts": item.get("repostCount", 0),
            "views": item.get("viewCount", 0),
            "replies": item.get("replyCount", 0),
            "bookmarks": item.get("bookmarkCount", 0),
            "account": account.get("username", ""),
            "is_verified": account.get("isVerified", False),
            "is_smart": item.get("repostBreakdown", {}).get("smart", 0) > 0,
            "smart_reposts": item.get("repostBreakdown", {}).get("smart", 0),
            "ct_reposts": item.get("repostBreakdown", {}).get("ct", 0),
            "mentioned_at": item.get("mentionedAt", ""),
            "type": item.get("type", "post"),
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
    # Handle nested: data.data, data.tokens, data.items
    if isinstance(raw, dict):
        raw = raw.get("data", raw.get("tokens", raw.get("items", [])))
    if isinstance(raw, dict):
        raw = [raw]

    for item in raw:
        if not isinstance(item, dict):
            continue
        results.append({
            "token": item.get("token", item.get("symbol", item.get("name", ""))),
            "mentions": item.get("current_count", item.get("mentionCount", item.get("mentions", 0))),
            "previous_mentions": item.get("previous_count", 0),
            "change_percent": item.get("change_percent", 0),
        })

    return results

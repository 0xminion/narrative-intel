"""Sentiment analysis using engagement heuristics from Elfa API data.

Since Elfa API returns metadata (likes, views, smart reposts) but NOT tweet text,
we use engagement patterns to infer sentiment:
- High engagement + smart account activity = bullish conviction
- High views but low engagement = noise/hype without substance
- High smart reposts = smart money attention
- Verified account activity = higher signal quality
- Bookmark ratio = deeper interest (people saving for later)
"""

import logging
from typing import Any

log = logging.getLogger(__name__)


def analyze_sentiment(narrative_mentions: dict[str, list[dict]], **kwargs) -> dict:
    """Analyze sentiment based on engagement patterns.

    Args:
        narrative_mentions: { "narrative_name": [mention dicts with engagement metadata] }

    Returns:
        { "narrative_name": { "score": int, "label": str, "counts": {}, "positive_reasons": [], "negative_reasons": [] } }
    """
    result = {}

    for narrative, mentions in narrative_mentions.items():
        if not mentions:
            result[narrative] = {
                "score": 0, "label": "MIXED",
                "counts": {"total": 0},
                "positive_reasons": ["No mentions data available"],
                "negative_reasons": [],
            }
            continue

        total = len(mentions)
        smart_reposts_total = sum(m.get("smart_reposts", 0) for m in mentions)
        ct_reposts_total = sum(m.get("ct_reposts", 0) for m in mentions)
        verified_count = sum(1 for m in mentions if m.get("is_verified"))
        total_likes = sum(m.get("likes", 0) for m in mentions)
        total_views = sum(m.get("views", 0) for m in mentions)
        total_reposts = sum(m.get("reposts", 0) for m in mentions)
        total_bookmarks = sum(m.get("bookmarks", 0) for m in mentions)
        total_replies = sum(m.get("replies", 0) for m in mentions)

        # Calculate engagement metrics
        avg_engagement = sum(m.get("engagement", 0) for m in mentions) / total if total else 0

        # Engagement ratio (likes + reposts + bookmarks) / views
        engaged_actions = total_likes + total_reposts + total_bookmarks
        engagement_ratio = engaged_actions / total_views if total_views > 0 else 0

        # Bookmark ratio (people saving = deep interest)
        bookmark_ratio = total_bookmarks / engaged_actions if engaged_actions > 0 else 0

        # Smart money signal
        smart_ratio = smart_reposts_total / total if total else 0

        # Reply depth (conversations happening)
        reply_ratio = total_replies / total if total else 0

        # Score calculation
        score = 0
        positive_reasons = []
        negative_reasons = []

        # Positive signals
        if smart_reposts_total > 0:
            smart_points = min(30, smart_reposts_total * 5)
            score += smart_points
            positive_reasons.append(f"{smart_reposts_total} smart account reposts detected")

        if ct_reposts_total > 5:
            ct_points = min(15, ct_reposts_total * 2)
            score += ct_points
            positive_reasons.append(f"{ct_reposts_total} CT reposts — Crypto Twitter paying attention")

        if engagement_ratio > 0.05:
            score += 15
            positive_reasons.append(f"High engagement ratio ({engagement_ratio:.1%}) — active participation, not passive scrolling")

        if bookmark_ratio > 0.1:
            score += 10
            positive_reasons.append(f"High bookmark rate ({bookmark_ratio:.1%}) — people saving this for reference")

        if verified_count > total * 0.3:
            score += 10
            positive_reasons.append(f"{verified_count} verified accounts involved — higher signal quality")

        if reply_ratio > 0.3:
            score += 5
            positive_reasons.append(f"Active discussions ({total_replies} replies) — genuine interest")

        # Negative signals
        if total_views > 1000000 and engagement_ratio < 0.01:
            score -= 20
            negative_reasons.append(f"Massive views ({total_views/1e6:.1f}M) but low engagement ({engagement_ratio:.1%}) — hype without conviction")

        if smart_reposts_total == 0 and total > 5:
            score -= 10
            negative_reasons.append("Zero smart account activity — retail only, no smart money interest")

        if total_bookmarks < total * 0.1 and total > 10:
            score -= 5
            negative_reasons.append("Low bookmark rate — content isn't being saved for later")

        if avg_engagement < 50 and total > 10:
            score -= 10
            negative_reasons.append(f"Low average engagement ({avg_engagement:.0f}) — weak social signal")

        # Clamp score
        score = max(-100, min(100, score))

        # Determine label
        if score >= 70:
            label = "EXTREME BULLISH"
        elif score >= 30:
            label = "SLIGHT BULLISH"
        elif score <= -70:
            label = "EXTREME BEARISH"
        elif score <= -30:
            label = "SLIGHT BEARISH"
        else:
            label = "MIXED"

        # Ensure at least one reason per side
        if not positive_reasons:
            positive_reasons.append("No strong positive signals detected in engagement data")
        if not negative_reasons:
            negative_reasons.append("No strong negative signals detected in engagement data")

        result[narrative] = {
            "score": score,
            "label": label,
            "counts": {
                "total_mentions": total,
                "smart_reposts": smart_reposts_total,
                "ct_reposts": ct_reposts_total,
                "verified_accounts": verified_count,
                "total_likes": total_likes,
                "total_views": total_views,
                "total_bookmarks": total_bookmarks,
            },
            "positive_reasons": positive_reasons[:3],
            "negative_reasons": negative_reasons[:3],
        }

    log.info(f"Sentiment analysis complete for {len(result)} narratives")
    return result

"""Report formatting for daily and weekly outputs."""

import logging
from datetime import datetime, timezone, timedelta
from analysis.signals import get_signal_display

log = logging.getLogger(__name__)

GMT8 = timezone(timedelta(hours=8))


def format_daily(narratives: list[dict], shifts: dict, velocity: dict,
                 boundary: list[dict], classified: dict, sentiment: dict,
                 questions: dict, cg_cross: list[dict], credits_used: int,
                 settings: dict) -> str:
    """Format the daily narrative shift report."""
    now = datetime.now(GMT8)
    date_str = now.strftime("%b %d")
    tokens_shift = settings.get("tokens_shift", 5)
    tokens_neutral = settings.get("tokens_neutral", 3)

    lines = []
    lines.append(f"📊 NARRATIVE SHIFT REPORT — {date_str}")
    lines.append(f"⏰ 09:00 GMT+8 | 📊 {credits_used} credits")
    lines.append("")

    # Positive shifts
    if shifts.get("positive"):
        lines.append("══════════════════════════════")
        lines.append("🔥 BIGGEST POSITIVE SHIFTS")
        lines.append("══════════════════════════════")
        lines.append("")

        for entry in shifts["positive"]:
            name = entry["name"]
            vel = velocity.get(name, "")
            vel_str = f" [3d: {vel}]" if vel else ""
            lines.append(f"▲ {name}: {entry['delta_display']}{vel_str}")

            # Sentiment
            sent = sentiment.get(name, {})
            if sent:
                sent_score = sent.get("score", 0)
                sent_label = sent.get("label", "MIXED")
                sent_emoji = _sentiment_emoji(sent_label)
                lines.append(f"  Sentiment: {sent_score:+d} ({sent_emoji} {sent_label})")

            # Tokens
            narrative_tokens = _get_narrative_tokens(classified, name)
            if narrative_tokens:
                lines.append("")
                lines.append("  Tokens:")
                for t in narrative_tokens[:tokens_shift]:
                    lines.append(f"  • {_format_token_line(t)}")

            # Sentiment reasons
            if sent:
                lines.append("")
                if sent.get("positive_reasons"):
                    lines.append("  Why bullish:")
                    for r in sent["positive_reasons"][:2]:
                        lines.append(f"  • {r}")
                if sent.get("negative_reasons"):
                    lines.append("  Why cautious:")
                    for r in sent["negative_reasons"][:2]:
                        lines.append(f"  • {r}")

            # Think about questions
            nq = questions.get(name, [])
            if nq:
                lines.append("")
                lines.append("  💭 Think about:")
                for q in nq[:2]:
                    lines.append(f"  → {q}")

            lines.append("")

    # Negative shifts
    if shifts.get("negative"):
        lines.append("══════════════════════════════")
        lines.append("📉 BIGGEST NEGATIVE SHIFTS")
        lines.append("══════════════════════════════")
        lines.append("")

        for entry in shifts["negative"]:
            name = entry["name"]
            lines.append(f"▼ {name}: {entry['delta_display']}")

            sent = sentiment.get(name, {})
            if sent:
                sent_score = sent.get("score", 0)
                sent_label = sent.get("label", "MIXED")
                sent_emoji = _sentiment_emoji(sent_label)
                lines.append(f"  Sentiment: {sent_score:+d} ({sent_emoji} {sent_label})")

            narrative_tokens = _get_narrative_tokens(classified, name)
            if narrative_tokens:
                lines.append("")
                lines.append("  Tokens cooling:")
                for t in narrative_tokens[:tokens_shift]:
                    lines.append(f"  • {_format_token_line(t)}")

            nq = questions.get(name, [])
            if nq:
                lines.append("")
                lines.append("  💭 Think about:")
                for q in nq[:2]:
                    lines.append(f"  → {q}")

            lines.append("")

    # Neutral (compressed)
    if shifts.get("neutral"):
        lines.append("══════════════════════════════")
        lines.append("— STABLE NARRATIVES")
        lines.append("══════════════════════════════")
        lines.append("")

        for entry in shifts["neutral"]:
            name = entry["name"]
            narrative_tokens = _get_narrative_tokens(classified, name)
            token_strs = [f"${t['symbol']}" for t in narrative_tokens[:tokens_neutral]]
            token_display = " ".join(token_strs) if token_strs else "—"

            # Sentiment summary
            sent = sentiment.get(name, {})
            sent_note = ""
            if sent:
                sent_label = sent.get("label", "MIXED")
                sent_emoji = _sentiment_emoji(sent_label)
                sent_note = f" | {sent_emoji} {sent_label}"

            lines.append(f"— {name}: {entry['delta_display']} | {token_display}{sent_note}")

            # Brief think about for neutral
            nq = questions.get(name, [])
            if nq:
                lines.append(f"  💭 {nq[0]}")

        lines.append("")

    # Boundary watch
    if boundary:
        lines.append("══════════════════════════════")
        lines.append("👀 BOUNDARY WATCH")
        lines.append("══════════════════════════════")
        lines.append("")
        for b in boundary[:3]:
            lines.append(f"⚠️ {b['name']}: {b['note']} — approaching top 10")
        lines.append("")

    # Sector signals
    lines.append("══════════════════════════════")
    lines.append("💡 TODAY'S SECTOR SIGNALS")
    lines.append("══════════════════════════════")
    lines.append("")
    for entry in shifts.get("positive", [])[:3]:
        name = entry["name"]
        sent = sentiment.get(name, {})
        label = sent.get("label", "MIXED")
        lines.append(f"🔥 {name} — {label}, rank #{entry['current_rank']}")
    for entry in shifts.get("negative", [])[:2]:
        name = entry["name"]
        lines.append(f"🚫 {name} — cooling, consider caution")
    lines.append("")

    # CoinGecko cross-signals
    if cg_cross:
        lines.append("══════════════════════════════")
        lines.append("📈 COINGECKO CROSS-SIGNALS")
        lines.append("══════════════════════════════")
        lines.append("")
        lines.append("CoinGecko trending but NOT in Elfa top narratives:")
        for t in cg_cross[:3]:
            change = t.get("change_24h", 0)
            symbol = t.get("symbol", "")
            lines.append(f"• ${symbol} — {'+' if change > 0 else ''}{change:.1f}% 24h | 💰 Price first")
        lines.append("→ These might be tomorrow's narrative shifts")
        lines.append("")

    lines.append(f"══════════════════════════════")
    lines.append(f"📊 {credits_used} credits | Elfa + CoinGecko")

    return "\n".join(lines)


def format_weekly(agg: dict, themes: dict, questions: list[str],
                  token_progression: dict, cross_signals: list[str]) -> str:
    """Format the weekly highlights report."""
    now = datetime.now(GMT8)
    week_start = (now - timedelta(days=6)).strftime("%b %d")
    week_end = now.strftime("%b %d")

    lines = []
    lines.append(f"📊 WEEKLY NARRATIVE HIGHLIGHTS — {week_start}-{week_end}")
    lines.append(f"🏆 Compiled from daily reports | No API calls")
    lines.append("")

    # Narrative of the week
    if agg.get("best"):
        best = agg["best"]
        lines.append("══════════════════════════════")
        lines.append("🏆 NARRATIVE OF THE WEEK")
        lines.append("══════════════════════════════")
        lines.append("")
        lines.append(f"{best['name']}")
        lines.append(f"  Mon rank: #{best.get('start_rank', '?')} → Sun rank: #{best.get('end_rank', '?')}")
        lines.append(f"  Avg rank: {best.get('avg_rank', '?')} | Net movement: +{best.get('net_movement', 0)}")
        lines.append(f"  Dominated the week.")
        lines.append("")

    # Biggest themes
    lines.append("══════════════════════════════")
    lines.append("📖 BIGGEST THEMES THIS WEEK")
    lines.append("══════════════════════════════")
    lines.append("")

    if themes.get("positive"):
        lines.append("POSITIVE:")
        lines.append("")
        for i, theme in enumerate(themes["positive"], 1):
            lines.append(f"{i}. {theme.get('theme', 'Unknown')}")
            lines.append(f"   What happened: {theme.get('what_happened', '')}")
            lines.append(f"   Why it matters: {theme.get('why_it_matters', '')}")
            if theme.get("key_moments"):
                lines.append(f"   Key moments: {', '.join(theme['key_moments'])}")
            lines.append("")

    if themes.get("negative"):
        lines.append("NEGATIVE:")
        lines.append("")
        for i, theme in enumerate(themes["negative"], 1):
            lines.append(f"{i}. {theme.get('theme', 'Unknown')}")
            lines.append(f"   What happened: {theme.get('what_happened', '')}")
            lines.append(f"   Why it matters: {theme.get('why_it_matters', '')}")
            lines.append("")

    # Questions to research
    if questions:
        lines.append("══════════════════════════════")
        lines.append("🔍 QUESTIONS TO RESEARCH")
        lines.append("══════════════════════════════")
        lines.append("")
        for i, q in enumerate(questions, 1):
            lines.append(f"→ {q}")
            lines.append("")

    # Token signal progression
    if token_progression:
        lines.append("══════════════════════════════")
        lines.append("🔥 TOKEN SIGNAL PROGRESSION")
        lines.append("══════════════════════════════")
        lines.append("")
        for symbol, info in sorted(token_progression.items(),
                                    key=lambda x: x[1].get("days", 0), reverse=True)[:10]:
            days = info.get("days", 0)
            history = info.get("history", [])
            history_str = " → ".join(history[-7:])
            interpretation = _interpret_progression(history)
            lines.append(f"${symbol} — appeared {days}/7 days")
            lines.append(f"  Signal: {history_str}")
            lines.append(f"  → {interpretation}")
            lines.append("")

    # Cross-signal tracker
    if cross_signals:
        lines.append("══════════════════════════════")
        lines.append("📈 CROSS-SIGNAL TRACKER")
        lines.append("══════════════════════════════")
        lines.append("")
        lines.append("Last week's 'price first' tokens that became narratives:")
        for cs in cross_signals:
            lines.append(f"• {cs}")
        lines.append("")

    lines.append("══════════════════════════════")
    lines.append("📊 0 credits | Pure aggregation")

    return "\n".join(lines)


def _get_narrative_tokens(classified: dict, narrative_name: str) -> list[dict]:
    """Get tokens belonging to a narrative, sorted by signal strength."""
    tokens = []
    for symbol, info in classified.items():
        if info.get("narrative", "").lower() == narrative_name.lower():
            tokens.append(info)
    # Sort: double-confirmed first, then social-first, then price-first
    signal_order = {"double-confirmed": 0, "social-first": 1, "price-first": 2}
    tokens.sort(key=lambda t: signal_order.get(t.get("signal", ""), 3))
    return tokens


def _format_token_line(t: dict) -> str:
    """Format a single token display line."""
    symbol = t.get("symbol", "?")
    pd = t.get("price_data", {})
    change = pd.get("change_24h", 0)
    vol = pd.get("volume", 0)
    mcap = pd.get("market_cap", 0)
    signal = get_signal_display(t.get("signal", ""))

    change_str = f"{'+' if change > 0 else ''}{change:.1f}%" if change else "flat"
    vol_str = _format_number(vol) if vol else "—"
    mcap_str = _format_number(mcap) if mcap else "—"

    return f"${symbol} — {change_str} 24h | Vol {vol_str} | MCap {mcap_str} | {signal}"


def _format_number(n: float) -> str:
    """Format large numbers with K/M/B suffix."""
    if n >= 1e9:
        return f"${n/1e9:.1f}B"
    if n >= 1e6:
        return f"${n/1e6:.1f}M"
    if n >= 1e3:
        return f"${n/1e3:.0f}K"
    return f"${n:.0f}"


def _sentiment_emoji(label: str) -> str:
    """Get emoji for sentiment label."""
    return {
        "EXTREME BULLISH": "🔥",
        "SLIGHT BULLISH": "📈",
        "MIXED": "⚖️",
        "SLIGHT BEARISH": "📉",
        "EXTREME BEARISH": "💀",
    }.get(label, "⚖️")


def _interpret_progression(history: list[str]) -> str:
    """Interpret signal progression."""
    if not history:
        return "No data"
    if all(h == "social-first" for h in history):
        return "Consistent social buzz, price hasn't followed — investigate catalysts"
    if "double-confirmed" in history[-2:]:
        return "Early social conviction validated by price action"
    if history[-1] == "price-first" and "social-first" in history[:-1]:
        return "Price followed social — narrative confirmed"
    return "Mixed signals — monitor closely"

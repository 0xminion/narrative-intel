#!/usr/bin/env python3
"""Narrative Intel — Daily and Weekly crypto narrative shift reports.

Usage:
    python main.py daily      # Generate and deliver daily report
    python main.py weekly     # Generate and deliver weekly highlights
    python main.py cleanup    # Run 30-day retention cleanup only
    python main.py daily --no-telegram --format json  # Output to stdout only
"""

import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import load, DAILY_DIR, WEEKLY_DIR, STATE_DIR
from sources import elfa, coingecko
from analysis import shifts as shift_analysis
from analysis import sentiment as sentiment_analysis
from analysis import signals as signal_analysis
from analysis import prompts as prompt_analysis
from output import formatter, telegram as tg
from storage import state as state_storage
from storage import retention

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("narrative-intel")
CREDITS_PER_NARRATIVE = 1
CREDITS_TRENDING_NARRATIVES = 5
CREDITS_TRENDING_TOKENS = 1


def parse_args():
    """Parse command line arguments."""
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    command = args[0]
    no_telegram = "--no-telegram" in args
    fmt = "text"
    if "--format" in args:
        idx = args.index("--format")
        if idx + 1 < len(args):
            fmt = args[idx + 1]

    return {"command": command, "no_telegram": no_telegram, "format": fmt}


def run_daily(cfg: dict, no_telegram: bool = False, output_format: str = "text"):
    """Execute the daily narrative shift pipeline."""
    log.info("=== DAILY REPORT START ===")
    settings = cfg["settings"]
    credits_used = 0

    # Step 0: Cleanup old files
    retention.cleanup(DAILY_DIR, WEEKLY_DIR, STATE_DIR, settings["retention_days"], tz=cfg["timezone"])

    # Step 1: Fetch trending narratives (5 credits)
    log.info("Fetching trending narratives...")
    narratives = elfa.get_trending_narratives(
        cfg["elfa_key"],
        time_frame="day",
        max_narratives=settings["top_narratives"],
    )
    credits_used += CREDITS_TRENDING_NARRATIVES
    log.info(f"Got {len(narratives)} narratives")

    if not narratives:
        log.error("No narratives returned. Aborting.")
        return

    # Step 2: Free signals from CoinGecko (0 credits)
    log.info("Fetching CoinGecko signals...")
    cg_trending = coingecko.get_trending(limit=15)
    cg_gl = coingecko.get_top_gainers_losers(top=300)
    cg_gainers = cg_gl.get("gainers", [])
    cg_losers = cg_gl.get("losers", [])
    log.info(f"CoinGecko: {len(cg_trending)} trending, {len(cg_gainers)} gainers, {len(cg_losers)} losers")

    # Step 3: Token discovery per narrative (10 credits)
    log.info("Fetching keyword mentions per narrative...")
    narrative_mentions = {}
    narrative_tokens = {}
    for n in narratives:
        name = n["name"]
        keywords = n.get("keywords", [name.lower()])
        mentions = elfa.get_keyword_mentions(
            cfg["elfa_key"],
            keywords=keywords,
            time_window="24h",
            limit=30,
            search_type="or",
        )
        credits_used += CREDITS_PER_NARRATIVE
        narrative_mentions[name] = mentions
        # Elfa API doesn't return token/ticker per mention — use engagement data
        # Tokens will come from trending-tokens and CoinGecko instead
        narrative_tokens[name] = []
        log.info(f"  {name}: {len(mentions)} mentions")

    # Step 4: Emerging social tokens (1 credit)
    log.info("Fetching trending tokens (4h)...")
    emerging = elfa.get_trending_tokens(
        cfg["elfa_key"],
        time_window="4h",
        min_mentions=settings["min_mentions"],
    )
    credits_used += CREDITS_TRENDING_TOKENS
    log.info(f"Got {len(emerging)} emerging tokens")

    # Step 5: Cross-reference and validate (0 credits)
    log.info("Cross-referencing signals...")
    classified = signal_analysis.classify_tokens(
        all_tokens=narrative_tokens,
        narrative_tokens=narrative_tokens,
        cg_trending=cg_trending,
        cg_gainers=cg_gainers + cg_losers,
        emerging_tokens=emerging,
    )

    # Enrich with price data
    all_symbols = list(classified.keys())
    if all_symbols:
        log.info(f"Fetching prices for {len(all_symbols)} tokens...")
        prices = coingecko.get_prices_batch(all_symbols)
        classified = signal_analysis.enrich_with_prices(classified, prices)

    # Update signal history from previous state
    classified = signal_analysis.update_signal_history(classified, STATE_DIR, state_storage)

    # Step 6: Sentiment analysis (engagement-based)
    log.info("Running sentiment analysis...")
    sentiment = sentiment_analysis.analyze_sentiment(
        narrative_mentions=narrative_mentions,
    )

    # Step 7: Narrative shifts
    log.info("Analyzing narrative shifts...")
    shift_data = shift_analysis.analyze_shifts(narratives, STATE_DIR, tz=cfg["timezone"])
    velocity = shift_analysis.calculate_velocity(STATE_DIR, narratives, days=3, tz=cfg["timezone"])
    boundary = shift_analysis.boundary_watch(narratives, STATE_DIR)

    # Step 8: Generate questions from contradictions
    log.info("Generating questions...")
    contradictions = prompt_analysis.detect_contradictions(
        narratives, shift_data, classified, sentiment,
    )
    narratives_with_data = {n["name"]: n for n in narratives}
    questions = prompt_analysis.generate_questions(
        contradictions, narratives_with_data,
        cfg["llm_provider"], cfg["llm_model"], cfg["llm_key"], cfg["llm_base_url"],
    )

    # CoinGecko cross-signals: trending tokens NOT in Elfa's top narratives
    elfa_tokens = set(classified.keys())
    cg_cross = [t for t in cg_trending + cg_gainers if t["symbol"].upper() not in elfa_tokens]

    # Step 9: Format report
    log.info("Formatting report...")
    report = formatter.format_daily(
        narratives=narratives,
        shifts=shift_data,
        velocity=velocity,
        boundary=boundary,
        classified=classified,
        sentiment=sentiment,
        questions=questions,
        cg_cross=cg_cross,
        credits_used=credits_used,
        settings=settings,
        tz=cfg["timezone"],
        tz_display=cfg["timezone_display"],
    )

    # Step 10: Output
    if output_format == "agent":
        # Agent JSON: clean data for Hermes agent to enrich with x_search
        output = {
            "narratives": narratives,
            "shifts": shift_data,
            "velocity": velocity,
            "boundary": boundary,
            "classified_tokens": {k: {kk: vv for kk, vv in v.items()
                                        if kk != "signal_history"} 
                                  for k, v in classified.items()},
            "sentiment": sentiment,
            "questions": questions,
            "cg_cross": cg_cross,
            "cg_trending": cg_trending,
            "emerging_tokens": emerging,
            "credits_used": credits_used,
            "date": datetime.now(cfg["timezone"]).strftime("%Y-%m-%d"),
            "timezone_display": cfg["timezone_display"],
        }
        print(json.dumps(output, indent=2, default=str))
    elif output_format == "json":
        output = {
            "report": report,
            "narratives": narratives,
            "shifts": shift_data,
            "classified_tokens": {k: v for k, v in classified.items()},
            "sentiment": sentiment,
            "credits_used": credits_used,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print(report)

    # Save report to file
    today = datetime.now(cfg["timezone"]).strftime("%Y-%m-%d")
    report_path = DAILY_DIR / f"{today}.txt"
    with open(report_path, "w") as f:
        f.write(report)
    log.info(f"Report saved to {report_path}")

    # Save state (narratives + token signals in one call)
    state_storage.save_state(STATE_DIR, narratives, {"token_signals": {
        k: {"signal_history": v.get("signal_history", []), "days_appearing": v.get("days_appearing", 1)}
        for k, v in classified.items()
    }}, tz=cfg["timezone"])

    # Deliver
    if not no_telegram:
        log.info("Delivering to Telegram...")
        try:
            delivered = tg.send_to_destinations(
                destinations=cfg["destinations"],
                default_bot_token=cfg["bot_token"],
                text=report,
                report_type="daily",
            )
            log.info(f"Delivered to {delivered} destination(s)")
        except Exception as e:
            log.error(f"Telegram delivery failed: {e}")

    log.info(f"=== DAILY REPORT COMPLETE | {credits_used} credits ===")


def run_weekly(cfg: dict, no_telegram: bool = False, output_format: str = "text"):
    """Execute the weekly highlights pipeline. No Elfa API calls."""
    log.info("=== WEEKLY REPORT START ===")

    # Step 1: Load daily reports + states
    states = state_storage.load_week(STATE_DIR, days=7, tz=cfg["timezone"])
    log.info(f"Loaded {len(states)} daily states")

    if len(states) < 2:
        log.warning("Not enough daily states for weekly report (need at least 2)")
        return

    # Step 2: Aggregate narrative movements
    agg = _aggregate_weekly(states)

    # Step 3: Aggregate token signal progression
    token_progression = _aggregate_tokens(states)

    # Step 4: CoinGecko context (0 credits)
    cg_gl = coingecko.get_top_gainers_losers(top=300)

    # Step 5: Cross-signal tracker
    cross_signals = _track_cross_signals(DAILY_DIR)

    # Step 6: Generate themes and questions (LLM)
    log.info("Generating weekly themes...")
    themes = prompt_analysis.generate_weekly_themes(
        reports=[], agg=agg,
        provider=cfg["llm_provider"], model=cfg["llm_model"], api_key=cfg["llm_key"],
        base_url=cfg["llm_base_url"],
    )

    log.info("Generating weekly questions...")
    questions = prompt_analysis.generate_weekly_questions(
        reports=[], agg=agg, token_progression=token_progression,
        provider=cfg["llm_provider"], model=cfg["llm_model"], api_key=cfg["llm_key"],
        base_url=cfg["llm_base_url"],
    )

    # Step 7: Format
    report = formatter.format_weekly(
        agg=agg, themes=themes, questions=questions,
        token_progression=token_progression, cross_signals=cross_signals,
        tz=cfg["timezone"], tz_display=cfg["timezone_display"],
    )

    # Output
    if output_format == "json":
        print(json.dumps({"report": report, "agg": agg, "themes": themes,
                          "questions": questions}, indent=2, default=str))
    else:
        print(report)

    # Save
    now = datetime.now(cfg["timezone"])
    week_str = now.strftime("%Y-W%W")
    report_path = WEEKLY_DIR / f"weekly-{week_str}.txt"
    with open(report_path, "w") as f:
        f.write(report)
    log.info(f"Weekly report saved to {report_path}")

    # Deliver
    if not no_telegram:
        try:
            delivered = tg.send_to_destinations(
                destinations=cfg["destinations"],
                default_bot_token=cfg["bot_token"],
                text=report,
                report_type="weekly",
            )
            log.info(f"Delivered to {delivered} destination(s)")
        except Exception as e:
            log.error(f"Telegram delivery failed: {e}")

    log.info("=== WEEKLY REPORT COMPLETE | 0 credits ===")


def _aggregate_weekly(states: list[dict]) -> dict:
    """Aggregate narrative data across daily states."""
    narrative_ranks = {}  # {name: [rank_day1, rank_day2, ...]}

    for state in reversed(states):  # oldest first
        for n in state.get("narratives", []):
            name = n["name"]
            if name not in narrative_ranks:
                narrative_ranks[name] = {
                    "ranks": [],
                    "start_rank": None,
                    "end_rank": None,
                }
            narrative_ranks[name]["ranks"].append(n["rank"])

    # Calculate stats
    summary = {}
    best = None
    for name, data in narrative_ranks.items():
        ranks = data["ranks"]
        avg_rank = sum(ranks) / len(ranks) if ranks else 999
        start = ranks[0] if ranks else 999
        end = ranks[-1] if ranks else 999
        net = start - end  # positive = improved

        summary[name] = {
            "avg_rank": round(avg_rank, 1),
            "start_rank": start,
            "end_rank": end,
            "net_movement": net,
            "days_in_top10": sum(1 for r in ranks if r <= 10),
        }

        if best is None or net > best.get("net_movement", 0):
            best = {"name": name, **summary[name]}

    return {"summary": summary, "best": best}


def _aggregate_tokens(states: list[dict]) -> dict:
    """Aggregate token signal progression across daily states."""
    token_data = {}  # {symbol: {"days": N, "history": [...]}}

    for state in reversed(states):  # oldest first
        for symbol, info in state.get("token_signals", {}).items():
            if symbol not in token_data:
                token_data[symbol] = {"days": 0, "history": []}
            token_data[symbol]["days"] += 1
            # Take the latest signal from this day
            signals = info.get("signal_history", [])
            if signals:
                token_data[symbol]["history"].append(signals[-1])

    return token_data


def _track_cross_signals(daily_dir: Path) -> list[str]:
    """Check if any price-first tokens from earlier days became narratives."""
    # Simplified: just note tokens that appeared in cross-signals
    # A full implementation would compare day-over-day
    results = []
    for f in sorted(daily_dir.glob("*.txt"))[-7:]:
        text = f.read_text()
        if "Price first" in text:
            # Extract lines mentioning price first
            for line in text.split("\n"):
                if "Price first" in line and "$" in line:
                    results.append(line.strip())
    return results[:5]  # Return most recent 5


def run_cleanup(cfg: dict):
    """Run retention cleanup only."""
    settings = cfg["settings"]
    deleted = retention.cleanup(DAILY_DIR, WEEKLY_DIR, STATE_DIR, settings["retention_days"], tz=cfg["timezone"])
    print(f"Cleanup complete: {deleted} files deleted")


def main():
    args = parse_args()
    cfg = load()

    if args["command"] == "daily":
        run_daily(cfg, no_telegram=args["no_telegram"], output_format=args["format"])
    elif args["command"] == "weekly":
        run_weekly(cfg, no_telegram=args["no_telegram"], output_format=args["format"])
    elif args["command"] == "cleanup":
        run_cleanup(cfg)
    else:
        print(f"Unknown command: {args['command']}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()

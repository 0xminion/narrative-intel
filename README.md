# Narrative Intel

Daily and Weekly crypto narrative shift reports powered by Elfa API (social intelligence) and CoinGecko CLI (market validation). Delivered to Telegram.

## What It Does

**Daily Report (09:00 GMT+8):**
- Top 10 trending narratives from crypto Twitter
- Narrative shifts compared to yesterday (positive, negative, neutral)
- Token discovery per narrative with signal classification:
  - 🔥 Double confirmed — social + price agreeing
  - 📢 Social first — CT buzzing, price hasn't caught up (early signal)
  - 💰 Price first — price moving, CT hasn't noticed yet
- Sentiment analysis (extreme/slight positive/negative) with reasons
- Data-grounded "think about" questions from contradictions
- Boundary watch for narratives approaching top 10
- CoinGecko cross-signals

**Weekly Highlights (Sunday 09:05 GMT+8):**
- Narrative of the week
- Biggest themes (positive + negative) with analysis
- Token signal progression over 7 days
- Deep research questions from patterns
- Cross-signal tracker (did price-first tokens become narratives?)

## Quick Start

```bash
# 1. Clone
git clone <repo-url>
cd narrative-intel

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env with your API keys

cp config.yaml.example config.yaml
# Edit config.yaml with your Telegram chat ID(s) and preferences

# 4. Test
python main.py daily --no-telegram

# 5. Run for real
python main.py daily
python main.py weekly
```

## Prerequisites

- Python 3.10+
- CoinGecko CLI (`cg`) — install via `pip install coingecko-cli` or your preferred method
- Elfa API key ([docs.elfa.ai](https://docs.elfa.ai))
- Telegram bot token ([@BotFather](https://t.me/BotFather))
- LLM API key (OpenAI or Anthropic)

## Configuration

### `.env` (secrets — never commit)

```
ELFA_API_KEY=your_key
LLM_API_KEY=your_key
TELEGRAM_BOT_TOKEN=fallback_bot_token
```

### `config.yaml` (settings + destinations)

```yaml
bot_token: ""                    # falls back to TELEGRAM_BOT_TOKEN env var

llm:
  provider: "openai"            # openai or anthropic
  model: "gpt-4o-mini"          # or claude-sonnet-4-20250514

settings:
  top_narratives: 10
  min_mentions: 15
  tokens_per_narrative_shift: 5
  tokens_per_narrative_neutral: 3
  retention_days: 30
  sentiment_mentions: 30

destinations:
  - name: "main-channel"
    chat_id: "-1001234567890"
    daily: true
    weekly: true

  # Multiple destinations supported
  # - name: "signals-group"
  #   chat_id: "-1009876543210"
  #   bot_token: "different-bot-token"  # optional override
  #   daily: true
  #   weekly: false

  # Webhook delivery for external bots
  # - name: "external-bot"
  #   webhook_url: "https://other-service.com/report"
  #   format: "json"
  #   daily: true
  #   weekly: true
```

## Telegram Setup

### For a Channel:
1. Create a channel in Telegram
2. Add your bot as admin with "Post Messages" permission
3. Get the channel ID: forward a message from the channel to `@userinfobot`
4. Set `chat_id` in config.yaml (e.g., `-1001234567890`)

### For a Group:
1. Add your bot to the group
2. Get the group ID the same way
3. Set `chat_id` in config.yaml

### For a Private Chat:
1. Start a chat with your bot
2. Get your user ID from `@userinfobot`
3. Set `chat_id` as your user ID (positive number)

## Cron Setup

```bash
# Daily report at 09:00 GMT+8 (01:00 UTC)
0 1 * * * cd /path/to/narrative-intel && python main.py daily >> /var/log/narrative-daily.log 2>&1

# Weekly report on Sunday 09:05 GMT+8 (01:05 UTC)
5 1 * * 0 cd /path/to/narrative-intel && python main.py weekly >> /var/log/narrative-weekly.log 2>&1
```

## CLI Usage

```bash
# Daily report (default: send to Telegram)
python main.py daily

# Daily report (output to terminal only)
python main.py daily --no-telegram

# Daily report (JSON output)
python main.py daily --no-telegram --format json

# Weekly highlights
python main.py weekly

# Manual cleanup (30-day retention)
python main.py cleanup
```

## Sample Output

```
📊 NARRATIVE SHIFT REPORT — Apr 10
⏰ 09:00 GMT+8 | 📊 16 credits

══════════════════════════════
🔥 BIGGEST POSITIVE SHIFTS
══════════════════════════════

▲ AI Agents: #5 → #1 (+4) [3d: accelerating]
  Sentiment: +62 (📈 SLIGHT BULLISH)

  Tokens:
  • $VIRTUAL — +18.5% 24h | Vol $42.0M | MCap $380.0M | 🔥 Double confirmed
  • $AI16Z — +31.2% 24h | Vol $89.0M | MCap $1.2B | 🔥 Double confirmed
  • $OLM — +4.1% 24h | Vol $2.0M | MCap $15.0M | 📢 Social first

  Why bullish:
  • Smart accounts accumulating $VIRTUAL and $AI16Z with conviction
  Why cautious:
  • Token unlock concerns for $AI16Z in Q2 flagged by 2 accounts

  💭 Think about:
  → $OLM social-first for 3 days with only +4% price on $2M volume.
    Is this accumulation or dead narrative? Check dev activity.
```

## Data Retention

Reports and state files are automatically cleaned up after 30 days. The cleanup runs at the start of each daily pipeline. To adjust, change `retention_days` in config.yaml.

## Credit Budget

| Endpoint | Credits/Call | Calls/Day | Daily Total |
|----------|-------------|-----------|-------------|
| trending-narratives | 5 | 1 | 5 |
| keyword-mentions | 1 | 10 | 1 |
| trending-tokens | 1 | 1 | 1 |
| **Total** | | | **16** |

Weekly reports: 0 credits (reads from stored daily data).

Monthly: ~480 credits.

## Project Structure

```
narrative-intel/
├── main.py              # Entry point
├── config.py            # Configuration loader
├── config.yaml.example  # Config template
├── .env.example         # Secrets template
├── requirements.txt     # Python dependencies
├── sources/
│   ├── elfa.py          # Elfa API client
│   └── coingecko.py     # CoinGecko CLI wrapper
├── analysis/
│   ├── shifts.py        # Narrative shift detection + velocity
│   ├── sentiment.py     # LLM sentiment analysis (5-class)
│   ├── signals.py       # Token classification + progression
│   └── prompts.py       # Question generation from contradictions
├── output/
│   ├── formatter.py     # Report formatting
│   ├── telegram.py      # Multi-destination Telegram delivery
│   └── webhook.py       # Webhook delivery
├── storage/
│   ├── state.py         # State persistence
│   └── retention.py     # 30-day cleanup
└── reports/             # Runtime (gitignored)
    ├── daily/           # Daily report files
    ├── weekly/          # Weekly report files
    └── state/           # State snapshots
```

## External Bot Integration

If you want a different bot (not Telegram) to consume the reports:

**Option 1: File-based** — The script saves reports to `reports/daily/` and `reports/weekly/`. Any bot can watch these directories.

**Option 2: Webhook** — Configure a `webhook_url` destination in config.yaml. Reports are POST'd as JSON.

**Option 3: stdout JSON** — Run with `--format json --no-telegram` and pipe the output anywhere:
```bash
python main.py daily --format json --no-telegram | your-bot --stdin
```

## License

MIT

"""Telegram multi-destination delivery with message splitting."""

import logging
import time
import requests

log = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 4096
SPLIT_DELAY = 0.5  # seconds between split messages


def send(bot_token: str, chat_id: str, text: str, split: bool = True) -> bool:
    """Send a message to a Telegram chat. Handles splitting for long messages.

    Returns True if at least one message was sent successfully.
    """
    if not bot_token or not chat_id:
        log.error(f"Missing bot_token or chat_id")
        return False

    if len(text) <= MAX_MESSAGE_LENGTH:
        return _send_message(bot_token, chat_id, text)

    if not split:
        # Truncate
        truncated = text[:MAX_MESSAGE_LENGTH - 100] + "\n\n... (truncated)"
        return _send_message(bot_token, chat_id, truncated)

    # Split at natural boundaries
    chunks = _split_message(text)
    success = False
    for i, chunk in enumerate(chunks):
        if i > 0:
            time.sleep(SPLIT_DELAY)
        prefix = f"({i+1}/{len(chunks)}) " if len(chunks) > 1 else ""
        if _send_message(bot_token, chat_id, prefix + chunk):
            success = True

    return success


def send_to_destinations(destinations: list[dict], default_bot_token: str,
                         text: str, report_type: str = "daily") -> int:
    """Send to all matching destinations. Returns count of successful deliveries."""
    delivered = 0

    for dest in destinations:
        # Check if this destination wants this report type
        if report_type == "daily" and not dest.get("daily", True):
            continue
        if report_type == "weekly" and not dest.get("weekly", True):
            continue

        # Webhook destinations
        if dest.get("webhook_url"):
            if _send_webhook(dest["webhook_url"], text, dest.get("format", "text")):
                delivered += 1
                log.info(f"Delivered to webhook: {dest.get('name', dest['webhook_url'])}")
            continue

        # Telegram destinations
        chat_id = dest.get("chat_id")
        if not chat_id:
            log.warning(f"Destination {dest.get('name', 'unknown')} has no chat_id, skipping")
            continue

        bot_token = dest.get("bot_token", default_bot_token)
        split = dest.get("split", True)

        if send(bot_token, chat_id, text, split=split):
            delivered += 1
            log.info(f"Delivered to: {dest.get('name', chat_id)}")
        else:
            log.error(f"Failed to deliver to: {dest.get('name', chat_id)}")

    return delivered


def _send_message(bot_token: str, chat_id: str, text: str) -> bool:
    """Send a single message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        payload = {
            "chat_id": chat_id,
            "text": text,
        }
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            return True
        else:
            log.error(f"Telegram API error: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        log.error(f"Telegram send failed: {e}")
        return False


def _send_webhook(url: str, text: str, format: str = "text") -> bool:
    """Send report to a webhook URL."""
    try:
        if format == "json":
            payload = {"report": text, "type": "narrative-intel"}
        else:
            payload = {"text": text}

        resp = requests.post(url, json=payload, timeout=30)
        return resp.status_code < 400
    except Exception as e:
        log.error(f"Webhook send failed: {e}")
        return False


def _split_message(text: str) -> list[str]:
    """Split a long message at natural section boundaries."""
    if len(text) <= MAX_MESSAGE_LENGTH:
        return [text]

    chunks = []
    current = ""
    lines = text.split("\n")

    for line in lines:
        # Check if adding this line exceeds limit
        test = current + "\n" + line if current else line
        if len(test) > MAX_MESSAGE_LENGTH - 50:  # Leave buffer
            if current:
                chunks.append(current.strip())
            # If a single line is very long, hard-split it
            if len(line) > MAX_MESSAGE_LENGTH - 50:
                while line:
                    chunks.append(line[:MAX_MESSAGE_LENGTH - 50])
                    line = line[MAX_MESSAGE_LENGTH - 50:]
                current = ""
            else:
                current = line
        else:
            current = test

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text[:MAX_MESSAGE_LENGTH]]

"""Webhook delivery for external bot integration."""

import logging
import requests

log = logging.getLogger(__name__)


def send(url: str, text: str, report_type: str = "daily", fmt: str = "text") -> bool:
    """Send report to a webhook endpoint.

    Args:
        url: Webhook URL
        text: Report text
        report_type: "daily" or "weekly"
        fmt: "json" or "text"

    Returns True if successful.
    """
    try:
        if fmt == "json":
            payload = {
                "report": text,
                "type": report_type,
                "source": "narrative-intel",
            }
        else:
            payload = {"text": text}

        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code < 400:
            log.info(f"Webhook delivered to {url}")
            return True
        else:
            log.error(f"Webhook error {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        log.error(f"Webhook failed for {url}: {e}")
        return False

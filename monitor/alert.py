"""Post a short message to a Slack or Discord incoming webhook."""
import os

import httpx


def send_alert(message: str, webhook_url: str | None = None) -> bool:
    """Return True if the webhook accepted the message."""
    url = webhook_url or os.getenv("ALERT_WEBHOOK_URL")
    if not url:
        print("ALERT (no ALERT_WEBHOOK_URL set, not sent):", message)
        return False
    # Slack reads "text", Discord reads "content"; each ignores the other.
    try:
        resp = httpx.post(url, json={"text": message, "content": message}, timeout=10)
        resp.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        print(f"ALERT delivery failed: {exc}")
        return False

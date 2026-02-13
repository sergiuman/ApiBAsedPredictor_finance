"""Telegram notification (optional)."""

from __future__ import annotations

import logging

import requests

from src.utils import Config

logger = logging.getLogger("signal.notify")

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram(message: str, cfg: Config) -> bool:
    """Send a message via Telegram. Returns True on success, False otherwise.

    Silently skips if Telegram credentials are not configured.
    """
    if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
        logger.info("Telegram not configured, skipping notification")
        return False

    url = _TELEGRAM_API.format(token=cfg.telegram_bot_token)

    # Telegram has a 4096-char limit per message; truncate if needed
    if len(message) > 4000:
        message = message[:3997] + "..."

    payload = {
        "chat_id": cfg.telegram_chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        logger.info("Sending Telegram notification to chat_id=%s", cfg.telegram_chat_id)
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            logger.info("Telegram message sent successfully")
            return True
        else:
            logger.warning("Telegram API returned ok=false: %s", data.get("description"))
            return False
    except requests.RequestException as exc:
        logger.error("Failed to send Telegram message: %s", exc)
        return False

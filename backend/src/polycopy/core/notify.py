"""Fire-and-forget Telegram messages from any process (e.g. the worker).

Uses the Bot API directly so the worker doesn't need a python-telegram-bot
Application. No-ops when no token is configured; never raises into callers.
"""

import httpx

from polycopy.core.config import get_settings
from polycopy.core.logging import get_logger

log = get_logger(__name__)


async def notify_user(telegram_id: int, text: str) -> None:
    token = get_settings().telegram_bot_token
    if not token:
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": telegram_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
            )
    except Exception as exc:  # noqa: BLE001 - notifications must never break trading
        log.warning("notify.send_failed", telegram_id=telegram_id, error=str(exc))

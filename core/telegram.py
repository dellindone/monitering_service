import httpx
import traceback
from core.logger import get_logger

logger = get_logger(__name__)

_BOT_TOKEN: str = ""
_CHAT_ID: str   = ""


def configure(bot_token: str, chat_id: str) -> None:
    global _BOT_TOKEN, _CHAT_ID
    _BOT_TOKEN = bot_token
    _CHAT_ID   = chat_id


def _send(text: str) -> None:
    if not _BOT_TOKEN or not _CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{_BOT_TOKEN}/sendMessage"
        httpx.post(url, json={"chat_id": _CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=5)
    except Exception:
        logger.warning(f"Telegram send failed:\n{traceback.format_exc()}")


def notify_trade_entered(symbol: str, quantity: int, buy_price: float, sl_price: float) -> None:
    cost = buy_price * quantity
    _send(
        f"🟢 <b>Trade Entered</b>\n"
        f"Symbol   : <code>{symbol}</code>\n"
        f"Qty      : {quantity}\n"
        f"Buy Price: ₹{buy_price:.2f}\n"
        f"SL Price : ₹{sl_price:.2f}\n"
        f"Cost     : ₹{cost:,.0f}"
    )


def notify_trade_exited(symbol: str, quantity: int, buy_price: float, exit_price: float, pnl: float, close_reason: str = "SL Hit") -> None:
    emoji = "🟢" if pnl >= 0 else "🔴"
    _send(
        f"{emoji} <b>Trade Exited</b>\n"
        f"Symbol    : <code>{symbol}</code>\n"
        f"Qty       : {quantity}\n"
        f"Buy Price : ₹{buy_price:.2f}\n"
        f"Exit Price: ₹{exit_price:.2f}\n"
        f"P&amp;L       : ₹{pnl:+,.2f}\n"
        f"Closed By : {close_reason}"
    )


def notify_daily_summary(date: str, daily_pnl: float, trade_count: int, halted: bool, halted_reason: str | None) -> None:
    emoji  = "🟢" if daily_pnl >= 0 else "🔴"
    status = f"HALTED ({halted_reason})" if halted else "RUNNING"
    _send(
        f"📊 <b>Daily Summary — {date}</b>\n"
        f"Total P&amp;L  : {emoji} ₹{daily_pnl:+,.2f}\n"
        f"Trades    : {trade_count}\n"
        f"Status    : {status}"
    )


def notify_kill_switch(activated: bool, reason: str) -> None:
    emoji = "🚨" if activated else "✅"
    action = "ACTIVATED" if activated else "DEACTIVATED"
    _send(f"{emoji} <b>Kill Switch {action}</b>\nReason: {reason}")

import httpx
import traceback
from core.logger import get_logger
from core.charges import calculate_charges

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
    try:
        c = calculate_charges(symbol, quantity, buy_price, exit_price)
        net_pnl = pnl - c["total_charges"]
        net_emoji = "🟢" if net_pnl >= 0 else "🔴"
        charges_line = (
            f"\n<b>Charges Breakdown</b>\n"
            f"  Brokerage : ₹{c['brokerage']:.2f}\n"
            f"  STT       : ₹{c['stt']:.2f}\n"
            f"  Exchange  : ₹{c['exchange']:.2f}\n"
            f"  SEBI      : ₹{c['sebi']:.2f}\n"
            f"  Stamp Duty: ₹{c['stamp_duty']:.2f}\n"
            f"  IPFT      : ₹{c['ipft']:.2f}\n"
            f"  GST       : ₹{c['gst']:.2f}\n"
            f"  <b>Total     : ₹{c['total_charges']:.2f}</b>\n"
            f"\n{net_emoji} <b>Net P&amp;L  : ₹{net_pnl:+,.2f}</b>"
        )
    except Exception:
        charges_line = ""
        net_pnl = pnl

    _send(
        f"{emoji} <b>Trade Exited</b>\n"
        f"Symbol    : <code>{symbol}</code>\n"
        f"Qty       : {quantity}\n"
        f"Buy Price : ₹{buy_price:.2f}\n"
        f"Exit Price: ₹{exit_price:.2f}\n"
        f"Gross P&amp;L  : ₹{pnl:+,.2f}\n"
        f"Closed By : {close_reason}"
        f"{charges_line}"
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


def notify_eod_summary(date: str, closed_trades: list, open_trades: list, daily_pnl: float, halted: bool, halted_reason: str | None, account_label: str = "") -> None:
    total_gross = sum(t.pnl or 0 for t in closed_trades)
    total_net   = total_gross
    charges_total = 0.0

    header = f"📋 <b>EOD Summary — {date}</b>"
    if account_label:
        header += f" | <b>{account_label}</b>"
    lines = [header + "\n"]

    if closed_trades:
        lines.append(f"<b>Closed Trades ({len(closed_trades)})</b>")
        for t in closed_trades:
            emoji = "🟢" if (t.pnl or 0) >= 0 else "🔴"
            try:
                c = calculate_charges(t.symbol, int(t.quantity), t.buy_price, t.current_price or t.buy_price)
                net = (t.pnl or 0) - c["total_charges"]
                charges_total += c["total_charges"]
                charges_str = f" | Net: ₹{net:+,.0f}"
            except Exception:
                charges_str = ""
            lines.append(
                f"{emoji} <code>{t.symbol}</code> qty={int(t.quantity)} "
                f"buy=₹{t.buy_price:.2f} exit=₹{(t.current_price or 0):.2f} "
                f"P&amp;L: ₹{(t.pnl or 0):+,.0f}{charges_str}"
            )
        total_net = total_gross - charges_total
        lines.append("")

    if open_trades:
        lines.append(f"<b>Still Open ({len(open_trades)})</b>")
        for t in open_trades:
            lines.append(f"🔵 <code>{t.symbol}</code> qty={int(t.quantity)} buy=₹{t.buy_price:.2f} sl=₹{t.sl_price:.2f}")
        lines.append("")

    gross_emoji = "🟢" if total_gross >= 0 else "🔴"
    net_emoji   = "🟢" if total_net >= 0 else "🔴"
    status      = f"HALTED ({halted_reason})" if halted else "RUNNING"

    lines.append(f"{gross_emoji} <b>Gross P&amp;L : ₹{total_gross:+,.2f}</b>")
    if charges_total:
        lines.append(f"   Charges  : ₹{charges_total:,.2f}")
        lines.append(f"{net_emoji} <b>Net P&amp;L   : ₹{total_net:+,.2f}</b>")
    lines.append(f"Status     : {status}")

    _send("\n".join(lines))


def notify_readonly_eod_summary(date: str, account_label: str, open_positions: list[dict], closed_orders: list[dict]) -> None:
    """EOD summary for inactive (read-only) accounts — raw broker data, no DB."""
    lines = [f"📋 <b>EOD Summary — {date}</b> | <b>{account_label}</b>\n"]

    if closed_orders:
        lines.append(f"<b>Closed Today ({len(closed_orders)})</b>")
        for o in closed_orders:
            symbol = o.get("trading_symbol", "")
            qty    = o.get("quantity", 0)
            price  = o.get("average_fill_price", 0)
            lines.append(f"🔴 <code>{symbol}</code> qty={qty} exit=₹{float(price):.2f}")
        lines.append("")

    if open_positions:
        lines.append(f"<b>Still Open ({len(open_positions)})</b>")
        for p in open_positions:
            symbol    = p.get("trading_symbol", "")
            qty       = p.get("quantity", 0)
            avg_price = p.get("credit_price") or p.get("net_price") or 0
            lines.append(f"🔵 <code>{symbol}</code> qty={qty} avg=₹{float(avg_price):.2f}")
        lines.append("")

    if not closed_orders and not open_positions:
        lines.append("No activity today.")

    _send("\n".join(lines))


def notify_kill_switch(activated: bool, reason: str) -> None:
    emoji = "🚨" if activated else "✅"
    action = "ACTIVATED" if activated else "DEACTIVATED"
    _send(f"{emoji} <b>Kill Switch {action}</b>\nReason: {reason}")

"""
FNO Options charges calculator (Equity Options, NSE/BSE)
Rates as of April 1, 2026
"""


def calculate_charges(
    symbol: str,
    quantity: int,
    buy_price: float,
    sell_price: float,
) -> dict:
    is_bse = symbol.upper().startswith("SENSEX")

    buy_premium  = buy_price * quantity
    sell_premium = sell_price * quantity

    # ── BUY side ─────────────────────────────────────────────────────
    brokerage_buy      = 20.0
    stamp_duty         = buy_premium * 0.00003        # 0.003% on buy premium
    exchange_buy       = buy_premium * (0.000325 if is_bse else 0.0003503)
    sebi_buy           = buy_premium * 0.000001       # 0.0001%
    ipft_buy           = buy_premium * 0.000005       # 0.0005% (Investor Protection Fund)
    gst_buy            = (brokerage_buy + exchange_buy + sebi_buy) * 0.18
    total_buy          = brokerage_buy + stamp_duty + exchange_buy + sebi_buy + ipft_buy + gst_buy

    # ── SELL side ────────────────────────────────────────────────────
    brokerage_sell     = 20.0
    stt                = sell_premium * 0.0015        # 0.15% STT on sell premium
    exchange_sell      = sell_premium * (0.000325 if is_bse else 0.0003503)
    sebi_sell          = sell_premium * 0.000001      # 0.0001%
    ipft_sell          = sell_premium * 0.000005      # 0.0005%
    gst_sell           = (brokerage_sell + exchange_sell + sebi_sell) * 0.18
    total_sell         = brokerage_sell + stt + exchange_sell + sebi_sell + ipft_sell + gst_sell

    total_charges      = total_buy + total_sell

    return {
        "buy_premium":    round(buy_premium, 2),
        "sell_premium":   round(sell_premium, 2),
        "brokerage":      round(brokerage_buy + brokerage_sell, 2),
        "stt":            round(stt, 2),
        "exchange":       round(exchange_buy + exchange_sell, 2),
        "sebi":           round(sebi_buy + sebi_sell, 2),
        "stamp_duty":     round(stamp_duty, 2),
        "ipft":           round(ipft_buy + ipft_sell, 2),
        "gst":            round(gst_buy + gst_sell, 2),
        "total_charges":  round(total_charges, 2),
    }

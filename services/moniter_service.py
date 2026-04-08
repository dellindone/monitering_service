import asyncio
import traceback
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from brokers.base import BrokerRestAdapter, BrokerFeedAdapter, Segment
from brokers.factory import BrokerFactory
from brokers.groww.auth import GrowwAuth
from engine.trade_manager import TradeManager
from engine.stoploss_strategy import TrailingStoplossStrategy
from repository.trade_repository import trade_repo
from risk.daily_risk_manager import DailyRiskManager
from core.database import AsyncSessionFactory
from core.logger import get_logger
from config import get_settings
import core.telegram as tg

logger = get_logger(__name__)

_IST          = ZoneInfo("Asia/Kolkata")
_MARKET_OPEN  = dtime(9, 15)
_MARKET_CLOSE = dtime(15, 30)


def _is_market_open() -> bool:
    now = datetime.now(_IST).time()
    return _MARKET_OPEN <= now <= _MARKET_CLOSE


class MonitorService:

    def __init__(self):
        self._settings      = get_settings()
        self._trade_manager = TradeManager()
        self._risk          = DailyRiskManager()
        self._feed          = None

    async def start(self, rest_broker: BrokerRestAdapter, feed_broker: BrokerFeedAdapter) -> None:
        self._feed = feed_broker

        # Wire brokers into TradeManager
        self._trade_manager.initialise(
            rest_broker=rest_broker,
            feed_broker=feed_broker,
            on_trade_closed=self.on_trade_closed,
        )

        # Connect feed and start consuming price ticks
        self._feed.connect()
        self._feed.start()
        logger.info("MonitorService started — price feed active")

        # Resume any OPEN trades from DB (in case of restart)
        await self._resume_open_trades()

        # Start the external trade scan loop
        asyncio.create_task(self._external_scan_loop())

    async def stop(self) -> None:
        if self._feed:
            self._feed.disconnect()
        logger.info("MonitorService stopped")

    async def on_credentials_refresh(self, broker_name: str) -> None:
        """Called by CredentialManager when credentials are updated."""
        logger.info(f"Credential refresh triggered for broker: {broker_name}")
        try:
            # Re-authenticate broker
            if broker_name == "groww":
                GrowwAuth().refresh()

            # Disconnect old feed and reconnect with fresh auth
            if self._feed:
                self._feed.disconnect()

            new_rest = BrokerFactory.create_rest(broker_name)
            new_feed = BrokerFactory.create_feed(broker_name)

            self._feed = new_feed
            self._trade_manager.initialise(
                rest_broker=new_rest,
                feed_broker=new_feed,
                on_trade_closed=self.on_trade_closed,
            )

            self._feed.connect()
            self._feed.start()

            # Re-subscribe all currently monitored symbols
            open_trade_ids = self._trade_manager.get_open_trades()
            logger.info(f"Broker re-initialized | {len(open_trade_ids)} trades still monitored")

        except Exception:
            logger.error(traceback.format_exc())

    # ── on trade closed callback ──────────────────────────────────────

    async def on_trade_closed(self, trade_id: str, exit_price: float, pnl: float, symbol: str = "", quantity: int = 0, buy_price: float = 0.0, close_reason: str = "SL Hit") -> None:
        try:
            async with AsyncSessionFactory() as db:
                await trade_repo.close_trade(db, trade_id, exit_price, pnl)
                await trade_repo.update_daily_stat(db, pnl)

            self._risk.record_trade_close(pnl)
            logger.info(f"Trade closed handled: {trade_id} | pnl={pnl}")

            if symbol:
                tg.notify_trade_exited(symbol, quantity, buy_price, exit_price, pnl, close_reason=close_reason)

            # Daily summary after every close
            risk_status = self._risk.status()
            tg.notify_daily_summary(
                date         = risk_status["date"],
                daily_pnl    = risk_status["realized_pnl"],
                trade_count  = risk_status["trade_count"],
                halted       = risk_status["halted"],
                halted_reason= risk_status["halted_reason"],
            )
        except Exception:
            logger.error(traceback.format_exc())

    # ── resume open trades on startup ─────────────────────────────────

    async def _resume_open_trades(self) -> None:
        try:
            async with AsyncSessionFactory() as db:
                open_trades = await trade_repo.get_open_trades(db)

            if not open_trades:
                logger.info("No open trades to resume")
                return

            for trade in open_trades:
                self._trade_manager.register_trade(
                    trade_id  = str(trade.id),
                    symbol    = trade.symbol,
                    quantity  = int(trade.quantity),
                    buy_price = trade.buy_price,
                    sl_price  = trade.sl_price,
                    segment   = Segment.FNO,
                )
            logger.info(f"Resumed {len(open_trades)} open trade(s)")
        except Exception:
            logger.error(traceback.format_exc())

    # ── external trade scan ───────────────────────────────────────────

    async def _external_scan_loop(self) -> None:
        logger.info("External trade scan loop started")
        while True:
            try:
                await asyncio.sleep(self._settings.external_scan_interval)
                if not _is_market_open():
                    logger.debug("Market closed — skipping external scan")
                    continue
                await self._scan_external_trades()
            except asyncio.CancelledError:
                logger.info("External scan loop cancelled")
                break
            except Exception:
                logger.error(traceback.format_exc())

    async def _scan_external_trades(self) -> None:
        try:
            broker    = self._trade_manager._rest_broker
            positions = broker.get_positions()

            logger.debug(f"Raw positions from broker: {positions}")

            async with AsyncSessionFactory() as db:
                open_trades     = await trade_repo.get_open_trades(db)
                known_trade_map = {t.symbol: t for t in open_trades}

                # symbols currently open at broker (qty > 0)
                broker_symbols = set()
                strategy = TrailingStoplossStrategy()

                for pos in (positions or []):
                    if not isinstance(pos, dict):
                        logger.warning(f"Unexpected position format: {type(pos)} | {pos}")
                        continue

                    symbol = pos.get("trading_symbol")
                    qty    = pos.get("quantity", 0)

                    if not symbol or qty <= 0:
                        continue

                    broker_symbols.add(symbol)
                    buy_price, order_id = broker.get_latest_buy_order(symbol, Segment.FNO)
                    if not buy_price:
                        buy_price = float(pos.get("credit_price") or pos.get("net_price") or 0)

                    if symbol in known_trade_map:
                        existing = known_trade_map[symbol]
                        updates  = {}
                        if int(qty) != int(existing.quantity):
                            updates["quantity"] = qty
                            self._trade_manager.update_quantity(str(existing.id), qty)
                            logger.info(f"Trade qty updated: {symbol} {existing.quantity} → {qty}")
                        if not existing.broker_order_id and order_id:
                            updates["broker_order_id"] = order_id
                            logger.info(f"Trade order_id updated: {symbol} → {order_id}")
                        if updates:
                            await trade_repo.update_trade(db, str(existing.id), updates)
                        continue

                    sl_price = strategy.initial_sl(buy_price)
                    trade = await trade_repo.create_trade(db, {
                        "symbol":          symbol,
                        "quantity":        qty,
                        "buy_price":       buy_price,
                        "sl_price":        sl_price,
                        "state":           "OPEN",
                        "source":          "EXTERNAL",
                        "broker_order_id": order_id,
                    })
                    self._trade_manager.register_trade(
                        trade_id  = str(trade.id),
                        symbol    = symbol,
                        quantity  = qty,
                        buy_price = buy_price,
                        sl_price  = sl_price,
                        segment   = Segment.FNO,
                    )
                    logger.info(f"External trade detected: {symbol} qty={qty} buy={buy_price}")

                # ── Detect manually closed positions ──────────────────
                for symbol, trade in known_trade_map.items():
                    if symbol in broker_symbols:
                        continue  # still open at broker

                    # Skip if already being handled by SL monitor (still in memory)
                    if str(trade.id) in self._trade_manager._monitors:
                        continue

                    # Position gone from broker — manually closed from UI
                    # Try to get actual executed sell price from order history
                    exit_price = None
                    try:
                        exit_price = broker.get_recent_sell_price(symbol, Segment.FNO)
                    except Exception:
                        pass
                    if not exit_price:
                        try:
                            exchange   = "BSE" if symbol.upper().startswith("SENSEX") else "NSE"
                            exit_price = broker.get_ltp(symbol, Segment.FNO, exchange)
                        except Exception:
                            exit_price = trade.buy_price  # last fallback

                    pnl = round((exit_price - trade.buy_price) * trade.quantity, 2)

                    await trade_repo.update_trade(db, str(trade.id), {
                        "state":         "CLOSED",
                        "current_price": exit_price,
                        "pnl":           pnl,
                        "source":        "MANUAL_CLOSE",
                    })
                    await trade_repo.update_daily_stat(db, pnl)
                    self._trade_manager.deregister_trade(str(trade.id))
                    self._risk.record_trade_close(pnl)

                    logger.info(f"Manual close detected: {symbol} | exit≈{exit_price} | pnl={pnl}")
                    tg.notify_trade_exited(
                        symbol       = symbol,
                        quantity     = int(trade.quantity),
                        buy_price    = trade.buy_price,
                        exit_price   = exit_price,
                        pnl          = pnl,
                        close_reason = "Manually closed from Broker UI",
                    )

        except Exception:
            logger.error(traceback.format_exc())


monitor_service = MonitorService()

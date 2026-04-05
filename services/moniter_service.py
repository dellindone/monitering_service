import asyncio
import traceback

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

logger = get_logger(__name__)


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

    async def on_trade_closed(self, trade_id: str, exit_price: float, pnl: float) -> None:
        try:
            async with AsyncSessionFactory() as db:
                await trade_repo.close_trade(db, trade_id, exit_price, pnl)
                await trade_repo.update_daily_stat(db, pnl)

            self._risk.record_trade_close(pnl)
            logger.info(f"Trade closed handled: {trade_id} | pnl={pnl}")
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
            if not positions:
                return

            logger.debug(f"Raw positions from broker: {positions}")

            async with AsyncSessionFactory() as db:
                open_trades    = await trade_repo.get_open_trades(db)
                known_trade_map = {t.symbol: t for t in open_trades}

                strategy = TrailingStoplossStrategy()
                for pos in positions:
                    if not isinstance(pos, dict):
                        logger.warning(f"Unexpected position format: {type(pos)} | {pos}")
                        continue

                    symbol = pos.get("trading_symbol")
                    qty    = pos.get("quantity", 0)

                    if not symbol or qty <= 0:
                        continue

                    buy_price = float(pos.get("net_price", 0))

                    if symbol in known_trade_map:
                        # Check if qty changed (manual lots added)
                        existing = known_trade_map[symbol]
                        if int(qty) != int(existing.quantity):
                            await trade_repo.update_trade(db, str(existing.id), {"quantity": qty})
                            self._trade_manager.update_quantity(str(existing.id), qty)
                            logger.info(f"Trade qty updated: {symbol} {existing.quantity} → {qty}")
                        continue

                    sl_price = strategy.initial_sl(buy_price)

                    trade = await trade_repo.create_trade(db, {
                        "symbol":    symbol,
                        "quantity":  qty,
                        "buy_price": buy_price,
                        "sl_price":  sl_price,
                        "state":     "OPEN",
                        "source":    "EXTERNAL",
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

        except Exception:
            logger.error(traceback.format_exc())


monitor_service = MonitorService()

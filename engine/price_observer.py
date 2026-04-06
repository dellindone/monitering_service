import time
import traceback
from abc import ABC, abstractmethod
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from engine.trade_state import TradeStateMachine, TradeState
from engine.stoploss_strategy import StoplossStrategy
from engine.trade_command import SellCommand
from brokers.base import BrokerRestAdapter
from core.vix_tracker import vix_tracker
from core.logger import get_logger

logger = get_logger(__name__)

_IST          = ZoneInfo("Asia/Kolkata")
_MARKET_OPEN  = dtime(9, 15)
_MARKET_CLOSE = dtime(15, 30)

_SL_CONFIRM_SECS = 3   # trailing SL must stay breached for 3s before exit


def _is_market_open() -> bool:
    now = datetime.now(_IST).time()
    return _MARKET_OPEN <= now <= _MARKET_CLOSE


class PriceObserver(ABC):

    @abstractmethod
    def on_price_update(self, symbol: str, price: float) -> None:
        ...


class TradeMonitor(PriceObserver):

    def __init__(
        self,
        trade_id: str,
        symbol: str,
        quantity: int,
        buy_price: float,
        sl_price: float,
        broker: BrokerRestAdapter,
        strategy: StoplossStrategy,
        state_machine: TradeStateMachine,
        on_exit,   # callback(trade_id, exit_price, pnl, symbol, quantity, buy_price, close_reason)
    ):
        self.trade_id        = trade_id
        self.symbol          = symbol
        self.quantity        = quantity
        self.buy_price       = buy_price
        self.sl_price        = sl_price
        self._broker         = broker
        self._strategy       = strategy
        self._state          = state_machine
        self._on_exit        = on_exit
        self.paused          = False
        self._sl_breach_time = None   # used for trailing SL 3s confirmation

    def on_price_update(self, symbol: str, price: float) -> None:
        if symbol != self.symbol:
            return
        if self.paused:
            return
        if self._state.is_terminal():
            return
        if not _is_market_open():
            return

        try:
            # Always trail SL upward when price moves in our favour
            new_sl = self._strategy.update_sl(self.buy_price, self.sl_price, price)
            if new_sl > self.sl_price:
                logger.info(f"[{self.trade_id}] SL trailed {self.sl_price} → {new_sl} | price={price}")
                self.sl_price = new_sl

            if price <= self.sl_price:
                in_hard_sl_phase = self._strategy.is_hard_sl(self.buy_price, self.sl_price)

                if in_hard_sl_phase:
                    # Hard SL — exit immediately, no confirmation needed
                    logger.info(f"[{self.trade_id}] Hard SL hit | price={price} sl={self.sl_price} — exiting immediately")
                    self._sl_breach_time = None
                    self._exit(price)
                else:
                    # Trailing SL — require 3s continuous breach before exit
                    if self._sl_breach_time is None:
                        self._sl_breach_time = time.time()
                        logger.info(f"[{self.trade_id}] Trailing SL breach started | price={price} sl={self.sl_price}")
                    elif time.time() - self._sl_breach_time >= _SL_CONFIRM_SECS:
                        logger.info(f"[{self.trade_id}] Trailing SL confirmed ({_SL_CONFIRM_SECS}s) — exiting")
                        self._sl_breach_time = None
                        self._exit(price)
            else:
                if self._sl_breach_time is not None:
                    logger.info(f"[{self.trade_id}] Price recovered above SL — resetting breach timer")
                self._sl_breach_time = None

        except Exception:
            logger.error(traceback.format_exc())

    def _exit(self, exit_price: float) -> None:
        try:
            self._state.transition(TradeState.SL_HIT)

            cmd = SellCommand(
                broker=self._broker,
                symbol=self.symbol,
                quantity=self.quantity,
            )
            response = cmd.execute()

            # Try to get actual executed price from broker order status
            try:
                from brokers.base import Segment
                order_id = response.get("groww_order_id")
                if order_id:
                    for _ in range(3):
                        actual_price = self._broker.get_order_executed_price(order_id, Segment.FNO)
                        if actual_price:
                            exit_price = actual_price
                            logger.info(f"[{self.trade_id}] Actual exit price from order: {exit_price}")
                            break
                        time.sleep(0.5)
            except Exception:
                logger.warning(f"[{self.trade_id}] Could not fetch actual exit price, using tick price")

            pnl = round((exit_price - self.buy_price) * self.quantity, 2)
            self._state.transition(TradeState.CLOSED)

            logger.info(f"[{self.trade_id}] Trade closed | pnl={pnl}")
            self._on_exit(self.trade_id, exit_price, pnl, self.symbol, self.quantity, self.buy_price, "SL Hit")

        except Exception:
            logger.error(traceback.format_exc())

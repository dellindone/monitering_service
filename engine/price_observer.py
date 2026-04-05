import traceback
from abc import ABC, abstractmethod
from engine.trade_state import TradeStateMachine, TradeState
from engine.stoploss_strategy import StoplossStrategy
from engine.trade_command import SellCommand
from brokers.base import BrokerRestAdapter
from core.logger import get_logger

logger = get_logger(__name__)


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
        on_exit,   # callback(trade_id, exit_price, pnl)
    ):
        self.trade_id      = trade_id
        self.symbol        = symbol
        self.quantity      = quantity
        self.buy_price     = buy_price
        self.sl_price      = sl_price
        self._broker       = broker
        self._strategy     = strategy
        self._state        = state_machine
        self._on_exit      = on_exit
        self.paused        = False

    def on_price_update(self, symbol: str, price: float) -> None:
        if symbol != self.symbol:
            return

        if self.paused:
            return

        if self._state.is_terminal():
            return

        try:
            # Trail the SL up if price has moved in our favour
            new_sl = self._strategy.updated_sl(self.buy_price, self.sl_price, price)
            if new_sl > self.sl_price:
                logger.info(f"[{self.trade_id}] SL trailed {self.sl_price} → {new_sl} | price={price}")
                self.sl_price = new_sl

            # Check if SL is hit
            if price <= self.sl_price:
                logger.info(f"[{self.trade_id}] SL hit at price={price} sl={self.sl_price}")
                self._exit(price)

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
            cmd.execute()

            pnl = round((exit_price - self.buy_price) * self.quantity, 2)
            self._state.transition(TradeState.CLOSED)

            logger.info(f"[{self.trade_id}] Trade closed | pnl={pnl}")
            self._on_exit(self.trade_id, exit_price, pnl)

        except Exception:
            logger.error(traceback.format_exc())

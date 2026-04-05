import traceback
from engine.price_observer import TradeMonitor
from engine.trade_state import TradeStateMachine, TradeState
from engine.stoploss_strategy import TrailingStoplossStrategy
from engine.trade_command import BuyCommand
from brokers.base import BrokerRestAdapter, BrokerFeedAdapter, Segment
from core.logger import get_logger

logger = get_logger(__name__)


class TradeManager:
    _instance: "TradeManager" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._monitors: dict[str, TradeMonitor] = {}
            cls._instance._rest_broker: BrokerRestAdapter = None
            cls._instance._feed_broker: BrokerFeedAdapter = None
            cls._instance._on_trade_closed = None  # callback(trade_id, exit_price, pnl)
        return cls._instance

    def initialise(
        self,
        rest_broker: BrokerRestAdapter,
        feed_broker: BrokerFeedAdapter,
        on_trade_closed,
    ) -> None:
        self._rest_broker     = rest_broker
        self._feed_broker     = feed_broker
        self._on_trade_closed = on_trade_closed
        logger.info("TradeManager initialised")

    def register_trade(
        self,
        trade_id: str,
        symbol: str,
        quantity: int,
        buy_price: float,
        sl_price: float,
        segment: Segment = Segment.FNO,
    ) -> None:
        strategy     = TrailingStoplossStrategy()
        state        = TradeStateMachine(TradeState.OPEN)

        monitor = TradeMonitor(
            trade_id=trade_id,
            symbol=symbol,
            quantity=quantity,
            buy_price=buy_price,
            sl_price=sl_price,
            broker=self._rest_broker,
            strategy=strategy,
            state_machine=state,
            on_exit=self._handle_exit,
        )

        self._monitors[trade_id] = monitor
        self._feed_broker.subscribe([symbol], callback=self.on_price_tick)
        logger.info(f"Trade registered: {trade_id} | {symbol} | qty={quantity} | buy={buy_price} | sl={sl_price}")

    def deregister_trade(self, trade_id: str) -> None:
        if trade_id in self._monitors:
            del self._monitors[trade_id]
            logger.info(f"Trade deregistered: {trade_id}")

    def on_price_tick(self, symbol: str, price: float) -> None:
        for monitor in list(self._monitors.values()):
            if monitor.symbol == symbol:
                monitor.on_price_update(symbol, price)

    def _handle_exit(self, trade_id: str, exit_price: float, pnl: float, symbol: str = "", quantity: int = 0, buy_price: float = 0.0, close_reason: str = "SL Hit") -> None:
        try:
            self.deregister_trade(trade_id)
            if self._on_trade_closed:
                self._on_trade_closed(trade_id, exit_price, pnl, symbol, quantity, buy_price, close_reason)
        except Exception:
            logger.error(traceback.format_exc())

    def pause_trade(self, trade_id: str) -> None:
        if trade_id not in self._monitors:
            raise ValueError(f"Trade {trade_id} not being monitored")
        self._monitors[trade_id].paused = True
        logger.info(f"Trade monitoring paused: {trade_id}")

    def resume_trade(self, trade_id: str) -> None:
        if trade_id not in self._monitors:
            raise ValueError(f"Trade {trade_id} not being monitored")
        self._monitors[trade_id].paused = False
        logger.info(f"Trade monitoring resumed: {trade_id}")

    def update_quantity(self, trade_id: str, quantity: int) -> None:
        if trade_id in self._monitors:
            self._monitors[trade_id].quantity = quantity
            logger.info(f"Trade qty updated in monitor: {trade_id} | qty={quantity}")

    def get_open_trades(self) -> list[str]:
        return list(self._monitors.keys())
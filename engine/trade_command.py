import traceback
from abc import ABC, abstractmethod
from brokers.base import BrokerRestAdapter, TransactionType, OrderType, Segment, Product
from core.logger import get_logger
from core.exceptions import BrokerOrderError

logger = get_logger(__name__)


class TradeCommand(ABC):

    @abstractmethod
    def execute(self) -> dict:
        ...

    @abstractmethod
    def undo(self) -> dict:
        ...


class BuyCommand(TradeCommand):

    def __init__(
        self,
        broker: BrokerRestAdapter,
        symbol: str,
        quantity: int,
        segment: Segment = Segment.FNO,
        product: Product = Product.NRML,
    ):
        self._broker   = broker
        self._symbol   = symbol
        self._quantity = quantity
        self._segment  = segment
        self._product  = product
        self._order_id = None

    def execute(self) -> dict:
        try:
            response = self._broker.place_order(
                symbol=self._symbol,
                quantity=self._quantity,
                transaction_type=TransactionType.BUY,
                order_type=OrderType.MARKET,
                segment=self._segment,
                product=self._product,
            )
            self._order_id = response.get("groww_order_id")
            logger.info(f"BuyCommand executed: {self._symbol} qty={self._quantity} order_id={self._order_id}")
            return response
        except Exception as e:
            logger.error(traceback.format_exc())
            raise BrokerOrderError(f"BuyCommand failed for {self._symbol}: {e}")

    def undo(self) -> dict:
        """Best-effort reversal — place a market sell."""
        try:
            response = self._broker.place_order(
                symbol=self._symbol,
                quantity=self._quantity,
                transaction_type=TransactionType.SELL,
                order_type=OrderType.MARKET,
                segment=self._segment,
                product=self._product,
            )
            logger.info(f"BuyCommand undone (sell placed): {self._symbol} qty={self._quantity}")
            return response
        except Exception as e:
            logger.error(traceback.format_exc())
            raise BrokerOrderError(f"BuyCommand undo failed for {self._symbol}: {e}")


class SellCommand(TradeCommand):

    def __init__(
        self,
        broker: BrokerRestAdapter,
        symbol: str,
        quantity: int,
        segment: Segment = Segment.FNO,
        product: Product = Product.NRML,
    ):
        self._broker   = broker
        self._symbol   = symbol
        self._quantity = quantity
        self._segment  = segment
        self._product  = product
        self._order_id = None

    def execute(self) -> dict:
        try:
            response = self._broker.place_order(
                symbol=self._symbol,
                quantity=self._quantity,
                transaction_type=TransactionType.SELL,
                order_type=OrderType.MARKET,
                segment=self._segment,
                product=self._product,
            )
            self._order_id = response.get("groww_order_id")
            logger.info(f"SellCommand executed: {self._symbol} qty={self._quantity} order_id={self._order_id}")
            return response
        except Exception as e:
            logger.error(traceback.format_exc())
            raise BrokerOrderError(f"SellCommand failed for {self._symbol}: {e}")

    def undo(self) -> dict:
        """Best-effort reversal — place a market buy back."""
        try:
            response = self._broker.place_order(
                symbol=self._symbol,
                quantity=self._quantity,
                transaction_type=TransactionType.BUY,
                order_type=OrderType.MARKET,
                segment=self._segment,
                product=self._product,
            )
            logger.info(f"SellCommand undone (buy placed): {self._symbol} qty={self._quantity}")
            return response
        except Exception as e:
            logger.error(traceback.format_exc())
            raise BrokerOrderError(f"SellCommand undo failed for {self._symbol}: {e}")
    
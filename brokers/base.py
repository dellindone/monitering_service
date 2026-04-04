from abc import ABC, abstractmethod
from enum import Enum

class TransactionType(str, Enum):
    BUY = 'BUY'
    SELL = 'SELL'

class OrderType(str, Enum):
    MARKET = 'MARKET'
    LIMIT = "LIMIT"
    STOP_LOSS = "SL"
    STOP_LOSS_MKT = "SL-M"

class Segment(str, Enum):
    CASH = "CASH"
    FNO = "FNO"

class Product(str, Enum):
    MIS = "MIS"
    CNC = "CNC"
    NRML = "NRML"

class BrokerRestAdapter(ABC):
    @abstractmethod
    def place_order(
        self,
        symbol: str,
        quantity: int,
        transaction_type: TransactionType,
        order_type: OrderType,
        segment: Segment,
        product: Product,
        price: float = 0.0
    ) -> dict:
        ...
    
    @abstractmethod
    def modify_order(
        self,
        # order_id: str,
        # quantity: int = None,
        # order_type: OrderType = None,
        # price: float = None,
    ) -> dict:
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> dict:
        ...
    
    @abstractmethod
    def get_positions(self) -> list[dict]:
        ...
    
    @abstractmethod
    def get_ltp(self, symbol: str, segment: Segment) -> float:
        ...

class BrokerFeedAdapter(ABC):

    @abstractmethod
    def subscribe(self, symbols: list[str], callback) -> None:
        ...

    @abstractmethod
    def unsubscribe(self, symbols: list[str]) -> None:
        ...

    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

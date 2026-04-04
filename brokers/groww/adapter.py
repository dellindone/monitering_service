import traceback
from growwapi import GrowwAPI
from brokers.base import BrokerRestAdapter, Product, Segment, OrderType, TransactionType
from brokers.groww.auth import GrowwAuth
from core.logger import get_logger
from core.exceptions import BrokerDataError, BrokerNetworkError, BrokerOrderError

logger = get_logger(__name__)

class GrowwAdapter(BrokerRestAdapter):
    def __init__(self):
        self._auth = GrowwAuth()
    
    @property
    def _client(self) -> GrowwAPI:
        return self._auth.get_client()
    
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
        try:
            response = self._client.place_order(
                trading_symbol=symbol,
                quantity=quantity,
                validity=self._client.VALIDITY_DAY,
                exchange=self._client.EXCHANGE_NSE,
                segment=segment.value,
                product=product.value,
                order_type=order_type.value,
                transaction_type=transaction_type.value,
                price=price,
            )
            logger.info(f"Order placed: {symbol} {transaction_type.value} qty={quantity} order_id={response.get('groww_order_id')}")
            return response
        except Exception as e:
            logger.error(traceback.format_exc())
            raise BrokerOrderError(f"Place Order Failed for {symbol}: {e}")
    
    def modify_order(
            self,
            order_id: str,
            quantity: int = None,
            order_type: OrderType = None,
            price: float = None,
    ):
        try:
            response = self._client.modify_order(
                groww_order_id=order_id,
                quantity=quantity,
                order_type=order_type.value if order_type else None,
                price=price,
            )
            logger.info(f"Order modified: order_id={order_id}")
            return response
        except Exception as e:
            logger.error(traceback.format_exc())
            raise BrokerOrderError(f"modify_order failed for {order_id}: {e}")

    def cancel_order(self, order_id: str) -> dict:
        try:
            response = self._client.cancel_order(order_id=order_id)
            logger.info(f"Order cancelled: order_id={order_id}")
            return response
        except Exception as e:
            logger.error(traceback.format_exc())
            raise BrokerOrderError(f"cancel_order failed for {order_id}: {e}")
    
    def get_positions(self) -> list[dict]:
        try:
            response = self._client.get_positions_for_user()
            return response.get("positions", [])
        except Exception as e:
            logger.error(traceback.format_exc())
            raise BrokerNetworkError(f"get_positions failed: {e}")
    
    def get_ltp(self, symbol: str, segment: Segment, exchange: str) -> float:
        try:
            key = f"{exchange}_{symbol}"
            result = self._client.get_ltp(
                segment=segment.value,
                exchange_trading_symbols=(key,),
            )
            if key not in result:
                raise BrokerDataError(f"LTP not found for {key}")
            return float(result.get(key))
        except BrokerDataError:
            raise
        except Exception as e:
            logger.error(traceback.format_exc())
            raise BrokerNetworkError(f"get_ltp failed for {symbol}: {e}")

from abc import ABC, abstractmethod
from config import get_settings

class StoplossStrategy(ABC):
    @abstractmethod
    def initial_sl(self, buy_price: float) -> float:
        ...
    
    @abstractmethod
    def update_sl(self, buy_price: float, current_sl: float, current_price: float) -> float:
        ...


class TrailingStoplossStrategy(StoplossStrategy):

    def __init__(self):
        settings = get_settings()
        self._sl_pct = settings.sl_percent / 100
        self._step_pct = settings.trailing_step / 100

    def initial_sl(self, buy_price: float) -> float:
        return round(buy_price * (1 - self._sl_pct), 2)
    
    def update_sl(self, buy_price: float, current_sl: float, current_price: float):
        if current_price <= buy_price:
            return current_sl

        # Trail SL directly from current price — always 5% below current price
        new_sl = round(current_price * (1 - self._sl_pct), 2)
        return max(new_sl, current_sl)  # SL only moves up, never down
    
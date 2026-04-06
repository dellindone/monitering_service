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
        gain = (current_price - buy_price) / buy_price
        bands_crossed = int(gain / self._step_pct)

        if bands_crossed <= 0:
            return current_sl

        # SL sits 5% below the last completed band level
        # e.g. buy=100, step=5%: band1=105, band2=110, band3=115...
        # at band1: SL = 105 * 0.95 = 99.75 (just under buy, protecting capital)
        # at band2: SL = 110 * 0.95 = 104.50
        # at band3: SL = 115 * 0.95 = 109.25
        band_price = buy_price * (1 + bands_crossed * self._step_pct)
        new_sl = round(band_price * (1 - self._sl_pct), 2)
        return max(new_sl, current_sl)  # never moves down
    
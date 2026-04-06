from abc import ABC, abstractmethod
from core.vix_tracker import vix_tracker


class StoplossStrategy(ABC):
    @abstractmethod
    def initial_sl(self, buy_price: float) -> float:
        ...

    @abstractmethod
    def update_sl(self, buy_price: float, current_sl: float, current_price: float) -> float:
        ...

    @abstractmethod
    def is_hard_sl(self, buy_price: float, current_sl: float) -> bool:
        ...


class TrailingStoplossStrategy(StoplossStrategy):

    def initial_sl(self, buy_price: float) -> float:
        params = vix_tracker.get_sl_params()
        return round(buy_price - params.sl_points, 2)

    def update_sl(self, buy_price: float, current_sl: float, current_price: float) -> float:
        params = vix_tracker.get_sl_params()
        breakeven_trigger = buy_price * (1 + params.breakeven_pct)

        if current_price < breakeven_trigger:
            return current_sl  # Phase 1: hard stop only, no trailing yet

        trail_points = max(params.trail_min, round(buy_price * params.trail_pct, 2))
        new_sl = round(current_price - trail_points, 2)
        return max(new_sl, current_sl)  # never moves down

    def is_hard_sl(self, buy_price: float, current_sl: float) -> bool:
        """True while SL is still at the initial hard stop level (before breakeven)."""
        params = vix_tracker.get_sl_params()
        return current_sl <= buy_price - params.sl_points + 0.01

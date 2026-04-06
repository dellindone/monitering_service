import asyncio
import traceback
from dataclasses import dataclass
from brokers.base import Segment
from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class SLParams:
    sl_points:     float
    trail_min:     float
    trail_pct:     float   # decimal, e.g. 0.12
    breakeven_pct: float   # decimal, e.g. 0.10


_VIX_BANDS = [
    (13,  SLParams(sl_points=20, trail_min=12, trail_pct=0.08, breakeven_pct=0.08)),
    (18,  SLParams(sl_points=30, trail_min=18, trail_pct=0.12, breakeven_pct=0.10)),
    (25,  SLParams(sl_points=40, trail_min=25, trail_pct=0.15, breakeven_pct=0.12)),
    (999, SLParams(sl_points=50, trail_min=35, trail_pct=0.18, breakeven_pct=0.15)),
]


class VixTracker:

    def __init__(self):
        self._vix: float = 18.0   # safe default — normal band
        self._broker = None

    def set_broker(self, broker) -> None:
        self._broker = broker

    def get_current_vix(self) -> float:
        return self._vix

    def get_sl_params(self) -> SLParams:
        for threshold, params in _VIX_BANDS:
            if self._vix < threshold:
                return params
        return _VIX_BANDS[-1][1]

    def _fetch_vix(self) -> float:
        result = self._broker._client.get_ltp(
            segment=Segment.CASH.value,
            exchange_trading_symbols=("NSE_INDIAVIX",),
        )
        return float(result["NSE_INDIAVIX"])

    async def start_refresh_loop(self) -> None:
        logger.info("VIX tracker started")
        while True:
            try:
                if self._broker:
                    vix = self._fetch_vix()
                    old = self._vix
                    self._vix = vix
                    params = self.get_sl_params()
                    if abs(vix - old) >= 0.5:
                        logger.info(
                            f"VIX updated: {old:.2f} → {vix:.2f} | "
                            f"sl={params.sl_points}pts trail={params.trail_min}pts/{params.trail_pct*100:.0f}% "
                            f"breakeven={params.breakeven_pct*100:.0f}%"
                        )
            except Exception:
                logger.warning(f"VIX fetch failed — using last value {self._vix:.2f}\n{traceback.format_exc()}")
            await asyncio.sleep(300)  # refresh every 5 minutes


vix_tracker = VixTracker()

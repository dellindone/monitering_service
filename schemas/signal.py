from pydantic import BaseModel
from typing import Literal

class SignalMessage(BaseModel):
    symbol: str
    contract: str
    category: Literal["INDEX", "STOCK", "COMMODITY"] = "INDEX"
    direction: Literal["BULLISH", "BEARISH"]
    ltp: float        # stock price
    option_ltp: float # option contract price
    lot_size: int = 1 # lot size from backend (default 1)
    investment: float # capital to deploy

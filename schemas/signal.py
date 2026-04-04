from pydantic import BaseModel
from typing import Literal

class SignalMessage(BaseModel):
    symbol: str
    contract: str
    direction: Literal["BULLISH", "BEARISH"]
    ltp: float        # stock price
    option_ltp: float # option contract price
    investment: float # capital to deploy

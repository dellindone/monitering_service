from enum import Enum
from core.exceptions import InvalidStateTransitionError


class TradeState(str, Enum):
    PENDING = "PENDING"   # order sent, awaiting fill
    OPEN    = "OPEN"      # fill confirmed, SL engine active
    SL_HIT  = "SL_HIT"   # SL triggered, exit order sent
    CLOSED  = "CLOSED"    # exit fill confirmed, P&L recorded
    FAILED  = "FAILED"    # order rejected by broker


# Valid transitions — only these are allowed
VALID_TRANSITIONS = {
    TradeState.PENDING: {TradeState.OPEN, TradeState.FAILED},
    TradeState.OPEN:    {TradeState.SL_HIT, TradeState.CLOSED},
    TradeState.SL_HIT:  {TradeState.CLOSED},
    TradeState.CLOSED:  set(),
    TradeState.FAILED:  set(),
}


class TradeStateMachine:

    def __init__(self, initial_state: TradeState = TradeState.PENDING):
        self.state = initial_state

    def transition(self, new_state: TradeState) -> None:
        allowed = VALID_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise InvalidStateTransitionError(self.state.value, new_state.value)
        self.state = new_state

    def is_terminal(self) -> bool:
        return self.state in {TradeState.CLOSED, TradeState.FAILED}
    
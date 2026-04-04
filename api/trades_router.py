from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from repository.trade_repository import trade_repo
from engine.trade_state import TradeState
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/trades", tags=["Trades"])


@router.get("")
async def get_trades(
    state: str = Query(None, description="Filter by state: OPEN, CLOSED, PENDING, FAILED"),
    db: AsyncSession = Depends(get_db),
):
    trade_state = TradeState(state) if state else None
    trades = await trade_repo.get_all_trades(db, state=trade_state)
    return {"trades": [_serialize(t) for t in trades]}


@router.get("/summary")
async def get_summary(db: AsyncSession = Depends(get_db)):
    from risk.daily_risk_manager import DailyRiskManager
    open_trades = await trade_repo.get_open_trades(db)
    risk_status = DailyRiskManager().status()
    return {
        "open_trade_count": len(open_trades),
        "daily_pnl":        risk_status["realized_pnl"],
        "halted":           risk_status["halted"],
        "halted_reason":    risk_status["halted_reason"],
        "date":             risk_status["date"],
    }


@router.get("/{trade_id}")
async def get_trade(trade_id: str, db: AsyncSession = Depends(get_db)):
    from core.exceptions import TradeNotFoundError
    trade = await trade_repo.get_trade(db, trade_id)
    if not trade:
        raise TradeNotFoundError(trade_id)
    return _serialize(trade)


def _serialize(trade) -> dict:
    return {
        "id":              str(trade.id),
        "symbol":          trade.symbol,
        "quantity":        trade.quantity,
        "buy_price":       trade.buy_price,
        "sl_price":        trade.sl_price,
        "current_price":   trade.current_price,
        "pnl":             trade.pnl,
        "state":           trade.state.value if trade.state else None,
        "source":          trade.source,
        "broker_order_id": trade.broker_order_id,
        "created_at":      str(trade.created_at),
        "updated_at":      str(trade.updated_at),
    }

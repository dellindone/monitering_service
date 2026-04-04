from fastapi import APIRouter
from pydantic import BaseModel
from risk.daily_risk_manager import DailyRiskManager
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/killswitch", tags=["Kill Switch"])


class KillSwitchRequest(BaseModel):
    active: bool
    reason: str = "manual"


@router.get("")
async def get_killswitch():
    return DailyRiskManager().status()


@router.post("")
async def set_killswitch(body: KillSwitchRequest):
    DailyRiskManager().set_halted(body.active, reason=body.reason)
    logger.info(f"Kill switch manually set to active={body.active} reason={body.reason}")
    return DailyRiskManager().status()

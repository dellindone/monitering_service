from fastapi import APIRouter
from pydantic import BaseModel
from config import get_settings
from core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/settings", tags=["Settings"])


class SettingsUpdate(BaseModel):
    sl_percent: float | None = None
    trailing_step: float | None = None
    daily_loss_limit: float | None = None
    daily_target: float | None = None
    capital_index_option: float | None = None
    capital_stock_option: float | None = None


@router.get("")
async def get_settings_view():
    s = get_settings()
    return {
        "sl_percent":           s.sl_percent,
        "trailing_step":        s.trailing_step,
        "daily_loss_limit":     s.daily_loss_limit,
        "daily_target":         s.daily_target,
        "capital_index_option": s.capital_index_option,
        "capital_stock_option": s.capital_stock_option,
    }


@router.patch("")
async def update_settings(body: SettingsUpdate):
    s = get_settings()
    if body.sl_percent is not None:
        s.sl_percent = body.sl_percent
    if body.trailing_step is not None:
        s.trailing_step = body.trailing_step
    if body.daily_loss_limit is not None:
        s.daily_loss_limit = body.daily_loss_limit
    if body.daily_target is not None:
        s.daily_target = body.daily_target
    if body.capital_index_option is not None:
        s.capital_index_option = body.capital_index_option
    if body.capital_stock_option is not None:
        s.capital_stock_option = body.capital_stock_option

    logger.info(f"Settings updated: {body.model_dump(exclude_none=True)}")
    return {"message": "Settings updated", "settings": {
        "sl_percent":           s.sl_percent,
        "trailing_step":        s.trailing_step,
        "daily_loss_limit":     s.daily_loss_limit,
        "daily_target":         s.daily_target,
        "capital_index_option": s.capital_index_option,
        "capital_stock_option": s.capital_stock_option,
    }}

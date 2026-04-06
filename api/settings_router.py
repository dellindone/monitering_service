from fastapi import APIRouter
from pydantic import BaseModel
from config import get_settings
from core.logger import get_logger
from core.vix_tracker import vix_tracker

logger = get_logger(__name__)
router = APIRouter(prefix="/settings", tags=["Settings"])


class SettingsUpdate(BaseModel):
    daily_loss_limit: float | None = None
    daily_target: float | None = None
    capital_index_option: float | None = None
    capital_stock_option: float | None = None
    lot_size_multiplier_nifty:     int | None = None
    lot_size_multiplier_banknifty: int | None = None
    lot_size_multiplier_sensex:    int | None = None
    lot_size_multiplier_stock:     int | None = None


@router.get("")
async def get_settings_view():
    s = get_settings()
    sl_params = vix_tracker.get_sl_params()
    return {
        "daily_loss_limit":     s.daily_loss_limit,
        "daily_target":         s.daily_target,
        "capital_index_option":          s.capital_index_option,
        "capital_stock_option":          s.capital_stock_option,
        "lot_size_multiplier_nifty":     s.lot_size_multiplier_nifty,
        "lot_size_multiplier_banknifty": s.lot_size_multiplier_banknifty,
        "lot_size_multiplier_sensex":    s.lot_size_multiplier_sensex,
        "lot_size_multiplier_stock":     s.lot_size_multiplier_stock,
        "vix_adaptive_sl": {
            "current_vix": vix_tracker.get_current_vix(),
            "sl_points": sl_params.sl_points,
            "trail_min": sl_params.trail_min,
            "trail_pct": sl_params.trail_pct,
            "breakeven_pct": sl_params.breakeven_pct,
        },
    }


@router.patch("")
async def update_settings(body: SettingsUpdate):
    s = get_settings()
    if body.daily_loss_limit is not None:
        s.daily_loss_limit = body.daily_loss_limit
    if body.daily_target is not None:
        s.daily_target = body.daily_target
    if body.capital_index_option is not None:
        s.capital_index_option = body.capital_index_option
    if body.capital_stock_option is not None:
        s.capital_stock_option = body.capital_stock_option
    if body.lot_size_multiplier_nifty is not None:
        s.lot_size_multiplier_nifty = max(1, body.lot_size_multiplier_nifty)
    if body.lot_size_multiplier_banknifty is not None:
        s.lot_size_multiplier_banknifty = max(1, body.lot_size_multiplier_banknifty)
    if body.lot_size_multiplier_sensex is not None:
        s.lot_size_multiplier_sensex = max(1, body.lot_size_multiplier_sensex)
    if body.lot_size_multiplier_stock is not None:
        s.lot_size_multiplier_stock = max(1, body.lot_size_multiplier_stock)

    logger.info(f"Settings updated: {body.model_dump(exclude_none=True)}")
    sl_params = vix_tracker.get_sl_params()
    return {"message": "Settings updated", "settings": {
        "daily_loss_limit":     s.daily_loss_limit,
        "daily_target":         s.daily_target,
        "capital_index_option": s.capital_index_option,
        "capital_stock_option": s.capital_stock_option,
        "lot_size_multiplier_nifty":     s.lot_size_multiplier_nifty,
        "lot_size_multiplier_banknifty": s.lot_size_multiplier_banknifty,
        "lot_size_multiplier_sensex":    s.lot_size_multiplier_sensex,
        "lot_size_multiplier_stock":     s.lot_size_multiplier_stock,
        "vix_adaptive_sl": {
            "current_vix": vix_tracker.get_current_vix(),
            "sl_points": sl_params.sl_points,
            "trail_min": sl_params.trail_min,
            "trail_pct": sl_params.trail_pct,
            "breakeven_pct": sl_params.breakeven_pct,
        },
    }}

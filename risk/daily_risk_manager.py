from datetime import datetime, timezone
from config import get_settings
from core.logger import get_logger

logger = get_logger(__name__)


class DailyRiskManager:
    _instance: "DailyRiskManager" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._realized_pnl  = 0.0
            cls._instance._trade_count   = 0
            cls._instance._halted        = False
            cls._instance._halted_reason = None
            cls._instance._date          = datetime.now(timezone.utc).date()
        return cls._instance

    # ── read ──────────────────────────────────────────────────────────

    def is_halted(self) -> bool:
        self._check_day_rollover()
        return self._halted

    def status(self) -> dict:
        return {
            "halted":        self._halted,
            "halted_reason": self._halted_reason,
            "realized_pnl":  self._realized_pnl,
            "trade_count":   self._trade_count,
            "date":          str(self._date),
        }

    # ── write ─────────────────────────────────────────────────────────

    def record_trade_close(self, pnl: float) -> None:
        self._realized_pnl += pnl
        self._trade_count  += 1
        logger.info(f"PnL recorded: {pnl} | daily_pnl={self._realized_pnl} | trades={self._trade_count}")
        self._evaluate()

    def set_halted(self, halted: bool, reason: str = "manual") -> None:
        self._halted        = halted
        self._halted_reason = reason if halted else None
        logger.info(f"Kill switch {'activated' if halted else 'deactivated'}: {reason}")

    def reset(self) -> None:
        self._realized_pnl  = 0.0
        self._trade_count   = 0
        self._halted        = False
        self._halted_reason = None
        self._date          = datetime.now(timezone.utc).date()
        logger.info("DailyRiskManager reset for new trading day")

    # ── internal ──────────────────────────────────────────────────────

    def _evaluate(self) -> None:
        settings = get_settings()

        if self._realized_pnl <= -abs(settings.daily_loss_limit):
            self.set_halted(True, reason="daily_loss_limit_hit")
            logger.warning(f"KILL SWITCH: daily loss limit hit | pnl={self._realized_pnl}")

        elif self._realized_pnl >= settings.daily_target:
            self.set_halted(True, reason="daily_target_hit")
            logger.warning(f"KILL SWITCH: daily target hit | pnl={self._realized_pnl}")

    def _check_day_rollover(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self._date:
            logger.info("New trading day detected — resetting DailyRiskManager")
            self.reset()

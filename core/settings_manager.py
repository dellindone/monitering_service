import traceback
from core.database import AsyncSessionFactory
from core.logger import get_logger

logger = get_logger(__name__)


class SettingsManager:
    _instance: "SettingsManager" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Defaults — overwritten on load()
            cls._instance.daily_loss_limit            = 5000.0
            cls._instance.daily_target                = 10000.0
            cls._instance.capital_index_option        = 50000.0
            cls._instance.capital_stock_option        = 25000.0
            cls._instance.lot_size_multiplier_nifty     = 1
            cls._instance.lot_size_multiplier_banknifty = 1
            cls._instance.lot_size_multiplier_sensex    = 1
            cls._instance.lot_size_multiplier_stock     = 1
            cls._instance.external_scan_interval      = 30
        return cls._instance

    async def load(self) -> None:
        """Load settings from DB into memory."""
        from repository.settings_repository import settings_repo
        try:
            async with AsyncSessionFactory() as db:
                row = await settings_repo.get(db)
                self.daily_loss_limit            = row.daily_loss_limit
                self.daily_target                = row.daily_target
                self.capital_index_option        = row.capital_index_option
                self.capital_stock_option        = row.capital_stock_option
                self.lot_size_multiplier_nifty     = row.lot_size_multiplier_nifty
                self.lot_size_multiplier_banknifty = row.lot_size_multiplier_banknifty
                self.lot_size_multiplier_sensex    = row.lot_size_multiplier_sensex
                self.lot_size_multiplier_stock     = row.lot_size_multiplier_stock
                self.external_scan_interval      = row.external_scan_interval
            logger.info("AppSettings loaded from DB")
        except Exception:
            logger.error(f"Failed to load settings from DB — using defaults:\n{traceback.format_exc()}")

    async def update(self, data: dict) -> None:
        """Update settings in DB and reload into memory."""
        from repository.settings_repository import settings_repo
        async with AsyncSessionFactory() as db:
            await settings_repo.update(db, data)
        await self.load()


settings_manager = SettingsManager()

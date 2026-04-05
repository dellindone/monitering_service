from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

ENV_FILE = Path(__file__).parent / ".env"

class Settings(BaseSettings):
    DEBUG: bool = False
    broker: str = "groww"
    groww_api_key : str
    groww_totp_secret: str

    # Capital
    capital_index_option: float = 50000.0
    capital_stock_option: float = 25000.0

    # Lot size multipliers
    lot_size_multiplier_nifty:     int = 1
    lot_size_multiplier_banknifty: int = 1
    lot_size_multiplier_sensex:    int = 1
    lot_size_multiplier_stock:     int = 1

    # Trailing SL
    sl_percent: float = 5.0
    trailing_step: float = 5.0

    # Kill switch
    daily_loss_limit: float = 5000.0
    daily_target: float = 10000.0

    # External scan
    external_scan_interval: int = 30

    # Database
    database_url: str

    backend_base_url: str
    backend_email: str
    backend_password: str

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str   = ""

    class Config:
        env_file = ENV_FILE
        env_file_encoding = "utf-8"
        extra = "ignore"

@lru_cache
def get_settings() -> Settings:
    return Settings()

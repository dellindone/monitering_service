import traceback
from core.database import AsyncSessionFactory
from repository.credentials_repository import credentials_repo
from core.logger import get_logger

logger = get_logger(__name__)


class CredentialManager:
    _instance: "CredentialManager" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._credentials: dict = {}       # broker_name → credentials dict
            cls._instance._active_broker: str = None
            cls._instance._refresh_callbacks: list = [] # called when credentials change
        return cls._instance

    # ── load ──────────────────────────────────────────────────────────

    async def load(self) -> None:
        """Load all credentials from DB into memory on startup."""
        try:
            async with AsyncSessionFactory() as db:
                all_records = await credentials_repo.get_all(db)
                for record in all_records:
                    self._credentials[record.broker_name] = record.credentials
                    if record.is_active:
                        self._active_broker = record.broker_name

            logger.info(f"Credentials loaded | active broker: {self._active_broker}")
        except Exception:
            logger.error(traceback.format_exc())
            raise

    # ── read ──────────────────────────────────────────────────────────

    def get(self, broker_name: str) -> dict:
        creds = self._credentials.get(broker_name)
        if not creds:
            raise ValueError(f"No credentials in memory for broker: {broker_name}")
        return creds

    def get_active_broker(self) -> str:
        if not self._active_broker:
            raise ValueError("No active broker set")
        return self._active_broker

    def get_inactive_accounts(self) -> list[dict]:
        """Return credentials for all non-active accounts."""
        inactive = []
        for broker_name, creds in self._credentials.items():
            if broker_name != self._active_broker:
                inactive.append({"broker_name": broker_name, **creds})
        return inactive

    # ── update ────────────────────────────────────────────────────────

    async def update(self, broker_name: str, credentials: dict) -> None:
        """Update credentials in DB and memory, then trigger refresh."""
        async with AsyncSessionFactory() as db:
            await credentials_repo.upsert(db, broker_name, credentials)

        self._credentials[broker_name] = credentials
        logger.info(f"Credentials updated in memory for broker: {broker_name}")

        if broker_name == self._active_broker:
            await self._trigger_refresh(broker_name)

    async def set_active_broker(self, broker_name: str) -> None:
        """Switch the active broker and trigger full re-initialization."""
        async with AsyncSessionFactory() as db:
            await credentials_repo.set_active(db, broker_name)

        self._active_broker = broker_name
        logger.info(f"Active broker switched to: {broker_name}")
        await self._trigger_refresh(broker_name)

    # ── refresh callbacks ─────────────────────────────────────────────

    def on_refresh(self, callback) -> None:
        """Register a callback to be called when credentials change."""
        self._refresh_callbacks.append(callback)

    async def _trigger_refresh(self, broker_name: str) -> None:
        logger.info(f"Triggering credential refresh for broker: {broker_name}")
        for callback in self._refresh_callbacks:
            try:
                await callback(broker_name)
            except Exception:
                logger.error(traceback.format_exc())


credential_manager = CredentialManager()

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
            cls._instance._accounts: dict = {}      # record_id → {broker_name, is_active, credentials...}
            cls._instance._active_id: str = None    # record_id of the active account
            cls._instance._refresh_callbacks: list = []
        return cls._instance

    # ── load ──────────────────────────────────────────────────────────

    async def load(self) -> None:
        """Load all credentials from DB into memory on startup."""
        try:
            async with AsyncSessionFactory() as db:
                all_records = await credentials_repo.get_all(db)
                self._accounts = {}
                for record in all_records:
                    rid = str(record.id)
                    self._accounts[rid] = {
                        "broker_name": record.broker_name,
                        "is_active":   record.is_active,
                        **(record.credentials or {}),
                    }
                    if record.is_active:
                        self._active_id = rid

            logger.info(f"Credentials loaded | {len(self._accounts)} account(s) | active_id={self._active_id}")
        except Exception:
            logger.error(traceback.format_exc())
            raise

    # ── read ──────────────────────────────────────────────────────────

    def get(self, broker_name: str) -> dict:
        """Return credentials for the active account (broker_name kept for compatibility)."""
        if not self._active_id:
            raise ValueError("No active broker set")
        return self._accounts[self._active_id]

    def get_active_broker(self) -> str:
        if not self._active_id:
            raise ValueError("No active broker set")
        return self._accounts[self._active_id]["broker_name"]

    def get_inactive_accounts(self) -> list[dict]:
        """Return credentials for all non-active accounts."""
        return [
            creds for rid, creds in self._accounts.items()
            if rid != self._active_id
        ]

    # ── update ────────────────────────────────────────────────────────

    async def update(self, broker_name: str, credentials: dict) -> None:
        """Update credentials in DB and memory, then trigger refresh if active."""
        async with AsyncSessionFactory() as db:
            await credentials_repo.upsert(db, broker_name, credentials)
        await self.load()

        if self._active_id and self._accounts[self._active_id]["broker_name"] == broker_name:
            await self._trigger_refresh(broker_name)

    async def set_active_broker(self, broker_name: str) -> None:
        async with AsyncSessionFactory() as db:
            await credentials_repo.set_active(db, broker_name)
        await self.load()
        await self._trigger_refresh(broker_name)

    # ── refresh callbacks ─────────────────────────────────────────────

    def on_refresh(self, callback) -> None:
        self._refresh_callbacks.append(callback)

    async def _trigger_refresh(self, broker_name: str) -> None:
        logger.info(f"Triggering credential refresh for broker: {broker_name}")
        for callback in self._refresh_callbacks:
            try:
                await callback(broker_name)
            except Exception:
                logger.error(traceback.format_exc())


credential_manager = CredentialManager()

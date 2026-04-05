from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.broker_credentials import BrokerCredential
from core.logger import get_logger

logger = get_logger(__name__)


class CredentialsRepository:

    async def get_active(self, db: AsyncSession) -> BrokerCredential | None:
        result = await db.execute(
            select(BrokerCredential).where(BrokerCredential.is_active == True)
        )
        return result.scalar_one_or_none()

    async def get_by_broker(self, db: AsyncSession, broker_name: str) -> BrokerCredential | None:
        result = await db.execute(
            select(BrokerCredential).where(BrokerCredential.broker_name == broker_name)
        )
        return result.scalars().first()

    async def get_all(self, db: AsyncSession) -> list[BrokerCredential]:
        result = await db.execute(select(BrokerCredential))
        return result.scalars().all()

    async def upsert(self, db: AsyncSession, broker_name: str, credentials: dict) -> BrokerCredential:
        """Always creates a new record — use update() to modify existing."""
        record = BrokerCredential(broker_name=broker_name, credentials=credentials)
        db.add(record)
        await db.commit()
        await db.refresh(record)
        logger.info(f"Credentials created for broker: {broker_name}")
        return record

    async def update(self, db: AsyncSession, record_id: str, credentials: dict) -> BrokerCredential:
        record = await db.get(BrokerCredential, record_id)
        if not record:
            raise ValueError(f"No credentials found for id: {record_id}")
        record.credentials = {**record.credentials, **credentials}
        record.updated_at  = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(record)
        logger.info(f"Credentials updated for: {record.broker_name} ({record_id})")
        return record

    async def set_active_by_id(self, db: AsyncSession, record_id: str) -> BrokerCredential:
        all_records = await self.get_all(db)
        for r in all_records:
            r.is_active = False
        record = await db.get(BrokerCredential, record_id)
        if not record:
            raise ValueError(f"No credentials found for id: {record_id}")
        record.is_active  = True
        record.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(record)
        logger.info(f"Active broker set to: {record.broker_name} ({record_id})")
        return record

    async def set_active(self, db: AsyncSession, broker_name: str) -> BrokerCredential:
        # Deactivate all brokers first
        all_records = await self.get_all(db)
        for r in all_records:
            r.is_active = False

        # Activate the selected broker
        record = await self.get_by_broker(db, broker_name)
        if not record:
            raise ValueError(f"No credentials found for broker: {broker_name}")

        record.is_active  = True
        record.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(record)
        logger.info(f"Active broker set to: {broker_name}")
        return record


credentials_repo = CredentialsRepository()

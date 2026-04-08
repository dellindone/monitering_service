from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.app_settings import AppSettings
from core.logger import get_logger

logger = get_logger(__name__)


class SettingsRepository:

    async def get(self, db: AsyncSession) -> AppSettings:
        result = await db.execute(select(AppSettings))
        row = result.scalar_one_or_none()
        if not row:
            row = AppSettings()
            db.add(row)
            await db.commit()
            await db.refresh(row)
            logger.info("AppSettings row created with defaults")
        return row

    async def update(self, db: AsyncSession, data: dict) -> AppSettings:
        row = await self.get(db)
        for key, value in data.items():
            if hasattr(row, key) and value is not None:
                setattr(row, key, value)
        await db.commit()
        await db.refresh(row)
        logger.info(f"AppSettings updated: {data}")
        return row


settings_repo = SettingsRepository()

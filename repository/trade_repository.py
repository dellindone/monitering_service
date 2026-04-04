from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from models.trade import Trade, DailyStat
from engine.trade_state import TradeState
from core.logger import get_logger

logger = get_logger(__name__)


class TradeRepository:

    # ── trades ────────────────────────────────────────────────────────

    async def create_trade(self, db: AsyncSession, data: dict) -> Trade:
        trade = Trade(**data)
        db.add(trade)
        await db.commit()
        await db.refresh(trade)
        logger.info(f"Trade created: {trade.id}")
        return trade

    async def get_trade(self, db: AsyncSession, trade_id: str) -> Trade | None:
        result = await db.execute(select(Trade).where(Trade.id == trade_id))
        return result.scalar_one_or_none()

    async def get_all_trades(self, db: AsyncSession, state: TradeState = None) -> list[Trade]:
        query = select(Trade)
        if state:
            query = query.where(Trade.state == state)
        result = await db.execute(query)
        return result.scalars().all()

    async def update_sl(self, db: AsyncSession, trade_id: str, sl_price: float) -> None:
        await db.execute(
            update(Trade)
            .where(Trade.id == trade_id)
            .values(sl_price=sl_price, updated_at=datetime.now(timezone.utc))
        )
        await db.commit()

    async def close_trade(self, db: AsyncSession, trade_id: str, exit_price: float, pnl: float) -> None:
        await db.execute(
            update(Trade)
            .where(Trade.id == trade_id)
            .values(
                state=TradeState.CLOSED,
                current_price=exit_price,
                pnl=pnl,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
        logger.info(f"Trade closed in DB: {trade_id} | pnl={pnl}")

    async def get_open_trades(self, db: AsyncSession) -> list[Trade]:
        return await self.get_all_trades(db, state=TradeState.OPEN)

    # ── daily stats ───────────────────────────────────────────────────

    async def get_or_create_daily_stat(self, db: AsyncSession) -> DailyStat:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        result = await db.execute(select(DailyStat).where(DailyStat.date == today))
        stat = result.scalar_one_or_none()
        if not stat:
            stat = DailyStat(date=today)
            db.add(stat)
            await db.commit()
            await db.refresh(stat)
        return stat

    async def update_daily_stat(self, db: AsyncSession, pnl: float) -> None:
        stat = await self.get_or_create_daily_stat(db)
        stat.realized_pnl += pnl
        stat.trade_count  += 1
        stat.updated_at    = datetime.now(timezone.utc)
        await db.commit()
        logger.info(f"Daily stat updated: pnl={pnl} | total={stat.realized_pnl}")


trade_repo = TradeRepository()

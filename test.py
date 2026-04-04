import asyncio
from sqlalchemy import text
from core.database import engine

async def test():
    async with engine.connect() as conn:
        result = await conn.execute(text('SELECT 1'))
        print('DB connection OK:', result.scalar())

asyncio.run(test())
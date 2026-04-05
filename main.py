import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from brokers.factory import BrokerFactory
from services.moniter_service import monitor_service
from services.signal_consumer import signal_consumer
from api.trades_router import router as trades_router
from api.killswitch_router import router as killswitch_router
from api.credentials_router import router as credentials_router
from api.settings_router import router as settings_router
from core.database import engine
from core.exceptions import AppException, BrokerException
from core.credential_manager import credential_manager
from models.trade import Base
from models.broker_credentials import BrokerCredential
from config import get_settings
from core.logger import get_logger
import core.telegram as tg

logger   = get_logger(__name__)
settings = get_settings()


async def _startup():
    """Heavy startup — runs in background so health check passes immediately."""
    logger.info("Starting Monitoring Service...")
    tg.configure(settings.telegram_bot_token, settings.telegram_chat_id)

    # Create DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready")

    # Seed + load credentials
    await _seed_credentials()
    await credential_manager.load()
    credential_manager.on_refresh(monitor_service.on_credentials_refresh)

    # Create broker adapters
    active_broker = credential_manager.get_active_broker()
    rest_broker   = BrokerFactory.create_rest(active_broker)
    feed_broker   = BrokerFactory.create_feed(active_broker)

    # Start monitor service + signal consumer
    await monitor_service.start(rest_broker, feed_broker)
    asyncio.create_task(signal_consumer.start())

    logger.info("Monitoring Service fully started")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run heavy startup in background — health check passes immediately
    startup_task = asyncio.create_task(_startup())

    yield

    # ── shutdown ──────────────────────────────────────────────────────
    logger.info("Shutting down Monitoring Service...")
    startup_task.cancel()
    await monitor_service.stop()
    await engine.dispose()
    logger.info("Shutdown complete")


async def _seed_credentials() -> None:
    """Seed initial Groww credentials from env vars if DB is empty."""
    from core.database import AsyncSessionFactory
    from repository.credentials_repository import credentials_repo

    async with AsyncSessionFactory() as db:
        existing = await credentials_repo.get_by_broker(db, settings.broker)
        if existing:
            logger.info(f"Credentials already in DB for broker: {settings.broker}")
            return

        # First run — seed from env vars
        creds = _build_env_credentials(settings.broker)
        if not creds:
            logger.warning(f"No env credentials found for broker: {settings.broker}")
            return

        await credentials_repo.upsert(db, settings.broker, creds)
        await credentials_repo.set_active(db, settings.broker)
        logger.info(f"Seeded credentials from env for broker: {settings.broker}")


def _build_env_credentials(broker_name: str) -> dict | None:
    """Build broker-specific credential dict from env vars."""
    if broker_name == "groww":
        if not settings.groww_api_key or not settings.groww_totp_secret:
            return None
        return {
            "api_key":     settings.groww_api_key,
            "totp_secret": settings.groww_totp_secret,
        }
    # Add other brokers here as needed
    return None


app = FastAPI(
    title="Trading Monitoring Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── global exception handlers ─────────────────────────────────────────

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(status_code=exc.code, content={"error": exc.message})


@app.exception_handler(BrokerException)
async def broker_exception_handler(request: Request, exc: BrokerException):
    return JSONResponse(status_code=exc.code, content={"error": exc.message})


# ── routers ───────────────────────────────────────────────────────────

app.include_router(trades_router)
app.include_router(killswitch_router)
app.include_router(credentials_router)
app.include_router(settings_router)


@app.get("/health")
async def health():
    return {"status": "ok"}

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from brokers.factory import BrokerFactory
from brokers.base import Segment
from core.vix_tracker import vix_tracker
from services.moniter_service import monitor_service
from services.signal_consumer import signal_consumer
from api.trades_router import router as trades_router
from api.killswitch_router import router as killswitch_router
from api.credentials_router import router as credentials_router
from api.settings_router import router as settings_router
from core.database import engine, AsyncSessionFactory
from core.exceptions import AppException, BrokerException
from core.credential_manager import credential_manager
from models.trade import Base
from models.broker_credentials import BrokerCredential
from repository.trade_repository import trade_repo
from risk.daily_risk_manager import DailyRiskManager
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

    # Wire VIX tracker and start refresh loop
    vix_tracker.set_broker(rest_broker)
    asyncio.create_task(vix_tracker.start_refresh_loop())

    # Start monitor service + signal consumer
    await monitor_service.start(rest_broker, feed_broker)
    asyncio.create_task(signal_consumer.start())
    asyncio.create_task(_eod_summary_loop())

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


_IST = ZoneInfo("Asia/Kolkata")
_EOD_HOUR, _EOD_MINUTE = 15, 35


async def _send_eod_summary() -> None:
    async with AsyncSessionFactory() as db:
        already_sent = await trade_repo.is_summary_sent(db)
        if already_sent:
            logger.info("EOD summary already sent today — skipping")
            return
        closed_trades = await trade_repo.get_today_closed_trades(db)
        open_trades   = await trade_repo.get_open_trades(db)

    risk        = DailyRiskManager()
    risk_status = risk.status()
    date_str    = datetime.now(_IST).strftime("%d %b %Y")

    tg.notify_eod_summary(
        date          = date_str,
        closed_trades = closed_trades,
        open_trades   = open_trades,
        daily_pnl     = risk_status["realized_pnl"],
        halted        = risk_status["halted"],
        halted_reason = risk_status["halted_reason"],
    )

    async with AsyncSessionFactory() as db:
        await trade_repo.mark_summary_sent(db)
    logger.info("EOD summary sent and marked in DB")

    # Send read-only EOD summaries for all inactive accounts
    for account in credential_manager.get_inactive_accounts():
        await _send_inactive_account_eod_summary(account, date_str)


async def _send_inactive_account_eod_summary(creds: dict, date_str: str) -> None:
    """Fetch positions + today's closed orders from an inactive broker account and send to Telegram."""
    from brokers.groww.auth import create_groww_client
    from datetime import date as date_type

    account_label = creds.get("account_label") or creds.get("broker_name", "Account 2")
    try:
        client = create_groww_client(creds)

        # Open positions
        pos_response  = client.get_positions_for_user()
        all_positions = pos_response.get("positions", [])
        open_positions = [
            p for p in all_positions
            if isinstance(p, dict) and int(p.get("quantity", 0)) > 0
        ]

        # Today's closed (SELL) orders
        today_str    = date_type.today().isoformat()
        order_result = client.get_order_list(segment=Segment.FNO.value, page_size=100)
        all_orders   = order_result.get("order_list", [])
        closed_orders = [
            o for o in all_orders
            if isinstance(o, dict)
            and o.get("transaction_type", "").upper() == "SELL"
            and o.get("order_status", "").upper() in {"EXECUTED", "COMPLETED"}
            and str(o.get("order_date", "") or o.get("created_at", "")).startswith(today_str)
        ]

        tg.notify_readonly_eod_summary(
            date          = date_str,
            account_label = account_label,
            open_positions = open_positions,
            closed_orders  = closed_orders,
        )
        logger.info(f"Inactive account EOD sent: {account_label}")
    except Exception:
        import traceback
        logger.error(f"Inactive account EOD failed for {account_label}:\n{traceback.format_exc()}")


async def _eod_summary_loop() -> None:
    """Fires at 15:35 IST. On startup, catches up if past 15:35 and summary not yet sent."""
    logger.info("EOD summary scheduler started")
    while True:
        try:
            now    = datetime.now(_IST)
            target = now.replace(hour=_EOD_HOUR, minute=_EOD_MINUTE, second=0, microsecond=0)

            if now >= target:
                # Past 15:35 today — check if summary was missed
                await _send_eod_summary()
                # Schedule for tomorrow
                target += timedelta(days=1)

            wait_secs = (target - now).total_seconds()
            logger.info(f"EOD summary scheduled in {wait_secs/60:.1f} min")
            await asyncio.sleep(wait_secs)
            await _send_eod_summary()

        except asyncio.CancelledError:
            logger.info("EOD summary loop cancelled")
            break
        except Exception:
            import traceback
            logger.error(f"EOD summary error:\n{traceback.format_exc()}")
            await asyncio.sleep(60)


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

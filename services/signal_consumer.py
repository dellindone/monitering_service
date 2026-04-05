import asyncio
import traceback
import json
import ssl
import certifi
import httpx
import websockets
from math import floor

from schemas.signal import SignalMessage
from engine.trade_manager import TradeManager
from engine.stoploss_strategy import TrailingStoplossStrategy
from engine.trade_command import BuyCommand
from brokers.base import Segment
from repository.trade_repository import trade_repo
from risk.daily_risk_manager import DailyRiskManager
from core.database import AsyncSessionFactory
from core.logger import get_logger
from config import get_settings

logger = get_logger(__name__)


class SignalConsumer:

    def __init__(self):
        self._settings      = get_settings()
        self._risk          = DailyRiskManager()
        self._trade_manager = TradeManager()
        self._access_token  = None
        self._refresh_token = None

    # ── auth ──────────────────────────────────────────────────────────

    def _ssl_context(self):
        ctx = ssl.create_default_context(cafile=certifi.where())
        return ctx

    async def _login(self) -> None:
        url = f"{self._settings.backend_base_url}/api/v1/auth/login"
        async with httpx.AsyncClient(follow_redirects=True, verify=certifi.where(), timeout=30) as client:
            response = await client.post(url, json={
                "email":    self._settings.backend_email,
                "password": self._settings.backend_password,
            })
            response.raise_for_status()
            data = response.json().get("data", response.json())
            self._access_token  = data["access_token"]
            self._refresh_token = data["refresh_token"]
            logger.info("Backend login successful")

    async def _refresh(self) -> None:
        url = f"{self._settings.backend_base_url}/api/v1/auth/refresh"
        async with httpx.AsyncClient(follow_redirects=True, verify=certifi.where(), timeout=30) as client:
            response = await client.post(url, params={"refresh_token": self._refresh_token})
            if response.status_code == 401:
                logger.warning("Refresh token expired — re-logging in")
                await self._login()
                return
            response.raise_for_status()
            data = response.json().get("data", response.json())
            self._access_token = data["access_token"]
            logger.info("Access token refreshed")

    async def _process_signal(self, signal: SignalMessage) -> None:
        if self._risk.is_halted():
            logger.warning(f"Kill switch active — skipping {signal.symbol}")
            return

        broker = self._trade_manager._rest_broker
        sym = signal.symbol.upper()
        if "BANKNIFTY" in sym:
            multiplier = self._settings.lot_size_multiplier_banknifty
        elif "NIFTY" in sym:
            multiplier = self._settings.lot_size_multiplier_nifty
        elif "SENSEX" in sym:
            multiplier = self._settings.lot_size_multiplier_sensex
        else:
            multiplier = self._settings.lot_size_multiplier_stock
        qty = signal.lot_size * multiplier

        if qty <= 0:
            logger.warning(f"qty=0 for {signal.contract}, skipping")
            return

        cmd      = BuyCommand(broker=broker, symbol=signal.contract, quantity=qty)
        response = cmd.execute()
        order_id = response.get("groww_order_id")

        strategy = TrailingStoplossStrategy()
        sl_price = strategy.initial_sl(signal.option_ltp)

        async with AsyncSessionFactory() as db:
            trade = await trade_repo.create_trade(db, {
                "symbol":          signal.contract,
                "quantity":        qty,
                "buy_price":       signal.option_ltp,
                "sl_price":        sl_price,
                "state":           "OPEN",
                "source":          "WEBSOCKET",
                "broker_order_id": order_id,
            })

        self._trade_manager.register_trade(
            trade_id  = str(trade.id),
            symbol    = signal.contract,
            quantity  = qty,
            buy_price = signal.option_ltp,
            sl_price  = sl_price,
            segment   = Segment.FNO,
        )
        logger.info(f"Trade live: {trade.id} | {signal.contract} | qty={qty} | sl={sl_price}")

    async def _handle_message(self, raw: str) -> None:
        try:
            signal = SignalMessage(**json.loads(raw))
            logger.info(f"Signal: {signal.symbol} {signal.direction} contract={signal.contract}")
            await self._process_signal(signal)
        except Exception:
            logger.error(traceback.format_exc())

    async def _connect_and_listen(self) -> None:
        ws_url = self._settings.backend_base_url.replace("http", "ws")
        url    = f"{ws_url}/ws/alerts?token={self._access_token}"
        logger.info(f"Connecting to backend WebSocket: {ws_url}/ws/alerts")

        try:
            async with websockets.connect(
                url,
                ssl=self._ssl_context(),
                ping_interval=30,
                ping_timeout=10,
            ) as ws:
                logger.info("Backend WebSocket connected successfully")
                async for raw in ws:
                    await self._handle_message(raw)
                logger.info("Backend WebSocket stream ended")
        except websockets.exceptions.InvalidStatusCode as e:
            logger.error(f"WebSocket handshake failed — HTTP {e.status_code} (check token/URL)")
            raise
        except websockets.exceptions.WebSocketException as e:
            logger.error(f"WebSocket error: {e}")
            raise
        except OSError as e:
            logger.error(f"WebSocket connection refused — is the backend running? {e}")
            raise

    async def start(self) -> None:
        logger.info("SignalConsumer starting...")
        await self._login()
        while True:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                logger.info("SignalConsumer cancelled")
                break
            except websockets.exceptions.ConnectionClosedError as e:
                logger.warning(f"WebSocket connection closed: code={e.code} reason={e.reason} — reconnecting in 3s")
                try:
                    await self._refresh()
                except Exception:
                    logger.warning("Token refresh failed — re-logging in")
                    try:
                        await self._login()
                    except Exception:
                        logger.error(f"Re-login failed:\n{traceback.format_exc()}")
                await asyncio.sleep(3)
            except Exception:
                logger.error(f"SignalConsumer unexpected error — reconnecting in 5s")
                logger.error(traceback.format_exc())
                await asyncio.sleep(5)


signal_consumer = SignalConsumer()

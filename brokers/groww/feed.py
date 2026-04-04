import asyncio
import traceback
import threading
from growwapi import GrowwFeed as _GrowwFeed
from brokers.base import BrokerFeedAdapter
from brokers.groww.auth import GrowwAuth
from core.logger import get_logger

logger = get_logger()

class GrowwFeed(BrokerFeedAdapter):
    def __init__(self):
        self._auth = GrowwAuth()
        self._feed: _GrowwFeed = None
        self._subscribe: list[str] = []
        self._callback = None
        self._thread: threading.Thread = None

    def connect(self):
        """Run GrowwFeed instantiation in a separate thread.
        GrowwFeed internally calls loop.run_until_complete() which
        cannot run inside FastAPI's already-running event loop.
        """
        try:
            client = self._auth.get_client()
            result = {}
            exc_holder = {}

            def _init():
                try:
                    result["feed"] = _GrowwFeed(client)
                except Exception as e:
                    exc_holder["err"] = e

            t = threading.Thread(target=_init)
            t.start()
            t.join()

            if "err" in exc_holder:
                raise exc_holder["err"]

            self._feed = result["feed"]
            logger.info("GrowwFeed connected")
        except Exception:
            logger.error(traceback.format_exc())
            raise
    
    def subscribe(self, symbols: list[str], callback) -> None:
        self._callback = callback
        self._subscribe.extend(symbols)

        def on_tick(meta):
            try:
                data = self._feed.get_ltp()
                for symbol, price in data.items():
                    callback(symbol, price)
            except Exception:
                logger.error(traceback.format_exc())
        
        self._feed.subscribe_ltp(symbols, on_data_received=on_tick)
        logger.info(f"Subscribed to symbol: {symbols}")
    
    def start(self) -> None:
        self._thread = threading.Thread(target=self._feed.consume, daemon=True)
        self._thread.start()
        logger.info("GrowwFeed consume thread started")
    
    def unsubscribe(self, symbols: list[str]) -> None:
        for s in symbols:
            if s in self._subscribe:
                self._subscribe.remove(s)
        logger.info(f"Unsubscribed from symbols: {symbols}")
    
    def disconnect(self):
        # GrowwFeed has no close() method — it runs in a daemon thread
        # and is terminated automatically when the process exits
        self._feed = None
        logger.info("GrowwFeed disconnected")

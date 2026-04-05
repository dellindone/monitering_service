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
        self._token_to_symbol: dict[str, str] = {}  # exchange_token -> trading_symbol

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

        # Resolve each trading symbol to the dict format Groww expects:
        # {"exchange": "NSE", "segment": "FNO", "exchange_token": "35100"}
        client = self._auth.get_client()
        instrument_list = []
        for sym in symbols:
            try:
                try:
                    inst = client.get_instrument_by_exchange_and_trading_symbol("NSE", sym)
                except Exception:
                    inst = client.get_instrument_by_exchange_and_trading_symbol("BSE", sym)
                token = str(inst["exchange_token"])
                instrument_list.append({
                    "exchange":       inst["exchange"],
                    "segment":        inst["segment"],
                    "exchange_token": token,
                })
                self._token_to_symbol[token] = sym
                logger.info(f"Resolved instrument: {sym} → token={token} exchange={inst['exchange']} segment={inst['segment']}")
            except Exception:
                logger.error(f"Could not resolve instrument for symbol '{sym}': {traceback.format_exc()}")

        if not instrument_list:
            logger.error(f"No valid instruments found for symbols: {symbols}")
            return

        def on_tick(meta):
            try:
                # get_ltp() returns {exchange: {segment: {exchange_token: price_data}}}
                data = self._feed.get_ltp()
                for _exchange, segs in data.items():
                    for _segment, tokens in segs.items():
                        for token, price_data in tokens.items():
                            sym = self._token_to_symbol.get(str(token))
                            if sym and price_data:
                                ltp = price_data.get("ltp")
                                if ltp is not None:
                                    callback(sym, float(ltp))
            except Exception:
                logger.error(traceback.format_exc())

        self._feed.subscribe_ltp(instrument_list, on_data_received=on_tick)
        logger.info(f"Subscribed to symbols: {symbols}")
    
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

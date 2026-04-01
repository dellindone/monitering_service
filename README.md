# Trading Monitoring Service

A production-grade, broker-agnostic trading monitoring service. Receives signals via webhook, punches trades through a broker adapter, tracks live prices via WebSocket, and enforces a trailing stop-loss engine — with daily kill switches and external trade detection.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Design Patterns](#design-patterns)
- [SOLID Principles](#solid-principles)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
  - [Webhook Flow](#1-webhook-flow)
  - [Trailing SL Engine](#2-trailing-sl-engine)
  - [Kill Switch](#3-kill-switch)
  - [External Trade Detection](#4-external-trade-detection)
  - [Capital Configuration](#5-capital-configuration)
- [Groww API Reference](#groww-api-reference)
- [Adding a New Broker](#adding-a-new-broker)
- [Configuration](#configuration)
- [API Endpoints](#api-endpoints)
- [Getting Started](#getting-started)

---

## Features

| # | Feature |
|---|---------|
| 1 | TradingView webhook receiver |
| 2 | Trade execution via broker API (Groww by default) |
| 3 | Live price feed via WebSocket |
| 4 | Trailing stop-loss engine (5% steps, configurable) |
| 5 | **Daily kill switch** — auto-halt on loss limit OR target hit |
| 6 | **External trade detection** — monitors trades punched manually |
| 7 | Multiple concurrent trade support |
| 8 | Capital config per instrument type (no broker balance API needed) |
| 9 | Plug-and-play broker swapping (Adapter pattern) |

---

## Architecture

```
┌──────────────┐     POST /webhook/signal
│  TradingView │ ─────────────────────────────────────────────────────────────┐
│    Alert     │                                                              │
└──────────────┘                                                              ▼
                                                                   ┌──────────────────┐
                                                                   │   API Layer       │
                                                                   │                  │
                                                                   │ webhook_router   │
                                                                   │ trades_router    │
                                                                   │ killswitch_router│
                                                                   └────────┬─────────┘
                                                                            │
                                                                            ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              SERVICES LAYER                                         │
│                                                                                     │
│  ┌────────────────────────────────┐       ┌─────────────────────────────────────┐  │
│  │       WebhookService           │       │         MonitorService              │  │
│  │                                │       │                                     │  │
│  │  1. validate secret            │       │  start_feed()                       │  │
│  │  2. check kill switch ◄──────► │◄─────►│  start_external_scan_loop() 60s    │  │
│  │  3. resolve symbol             │       │                                     │  │
│  │  4. compute qty from capital   │       └─────────────────────────────────────┘  │
│  │  5. BuyCommand.execute()       │                                                 │
│  │  6. register_trade()           │       ┌─────────────────────────────────────┐  │
│  └───────────────┬────────────────┘       │         DailyRiskManager            │  │
│                  │                        │           [KILL SWITCH]             │  │
│                  │                        │                                     │  │
│                  │                        │  daily_pnl  daily_loss  daily_target│  │
│                  │                        │  is_halted()                        │  │
│                  │                        │  record_trade_close(pnl)            │  │
│                  └───────────────────────►│  reset() at market open (9:15 AM)   │  │
│                                           └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              ENGINE LAYER                                           │
│                                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐                 │
│  │              TradeManager  [SINGLETON]                         │                 │
│  │                                                               │                 │
│  │   _monitors: { trade_id → TradeMonitor }                     │                 │
│  │                                                               │                 │
│  │   initialise(broker)      register_trade()                   │                 │
│  │   deregister_trade()      on_price_tick(symbol, price) ◄─────│──── WebSocket   │
│  │   scan_external_trades()                                      │                 │
│  └────────────────────┬──────────────────────────────────────── ┘                 │
│                        │ fans out to all monitors for symbol                        │
│                        ▼                                                            │
│  ┌───────────────────────────────────────────────────────────────┐                 │
│  │           TradeMonitor  [OBSERVER]  (one per trade)            │                 │
│  │                                                               │                 │
│  │   on_price_update(symbol, price)                             │                 │
│  │      │                                                        │                 │
│  │      ├── strategy.updated_sl(buy, current_sl, price)         │                 │
│  │      │       └── if new_sl > current_sl → repo.update_sl()   │                 │
│  │      │                                                        │                 │
│  │      └── if price <= sl_price                                │                 │
│  │              └── SellCommand.execute()  ────────────────────►│──► Broker API   │
│  │              └── daily_risk.record_trade_close(pnl)          │                 │
│  │              └── trade_repo.close_trade()                    │                 │
│  │              └── trade_manager.deregister_trade()            │                 │
│  └───────────────────────────────────────────────────────────── ┘                 │
│                                                                                     │
│  ┌──────────────────────────────┐   ┌──────────────────────────────────────────┐  │
│  │   TrailingStoplossStrategy   │   │         TradeStateMachine                │  │
│  │         [STRATEGY]           │   │              [STATE]                     │  │
│  │                              │   │                                          │  │
│  │  initial_sl = buy * 0.95     │   │  PENDING → OPEN → SL_HIT → CLOSED       │  │
│  │                              │   │                 ↓                        │  │
│  │  Bands (every 5%):           │   │              FAILED                      │  │
│  │  buy@100 → SL@95             │   └──────────────────────────────────────────┘  │
│  │  price@105 → SL@100          │                                                  │
│  │  price@110 → SL@105          │   ┌──────────────────────────────────────────┐  │
│  │  price@115 → SL@110          │   │        BuyCommand / SellCommand          │  │
│  └──────────────────────────────┘   │              [COMMAND]                   │  │
│                                     │  execute() → broker.place_order()        │  │
│                                     │  undo()    → reverse (best-effort)       │  │
│                                     └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           BROKER LAYER  [ADAPTER + FACTORY]                         │
│                                                                                     │
│   ┌─────────────────────────────────────────────────────────────────────────────┐  │
│   │                        BrokerAdapter  (Abstract)                             │  │
│   │                                                                              │  │
│   │   get_positions()   place_order()   get_ltp()                               │  │
│   │   subscribe_price_feed(symbols, callback)   disconnect_feed()               │  │
│   └──────────────────────────────────────────────────────────────────────────── ┘  │
│                  ▲                              ▲                    ▲              │
│     ┌────────────┴──────────┐    ┌─────────────┴──────┐  ┌─────────┴────────────┐ │
│     │    GrowwAdapter       │    │  ZerodhaAdapter     │  │   UpstoxAdapter      │ │
│     │    [CURRENT]          │    │  [plug & play]      │  │   [plug & play]      │ │
│     │  GrowwAuth (Singleton)│    └─────────────────────┘  └──────────────────────┘ │
│     │  GrowwPriceFeed (WS)  │                                                       │
│     └───────────────────────┘                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐  │
│   │  BrokerFactory.create("groww")  →  GrowwAdapter()                           │  │
│   │  BrokerFactory.register("zerodha", ZerodhaAdapter)  ← add new broker here  │  │
│   └─────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           REPOSITORY + DATABASE LAYER                               │
│                                                                                     │
│   ┌─────────────────────────────────────────────────────────────────────────────┐  │
│   │                TradeRepository + DailyStatsRepository  [REPOSITORY]          │  │
│   └──────────────────────────────────┬──────────────────────────────────────────┘  │
│                                       ▼                                             │
│                         ┌─────────────────────────┐                                │
│                         │  PostgreSQL (local)      │                                │
│                         │                          │                                │
│                         │  trades table            │                                │
│                         │  daily_stats table       │                                │
│                         └─────────────────────────┘                                │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              KILL SWITCH LOGIC                                      │
│                                                                                     │
│   Every trade close → DailyRiskManager.record_trade_close(pnl)                     │
│                                                                                     │
│          daily_loss >= DAILY_LOSS_LIMIT?  ──► HALT  (no new trades today)          │
│          daily_profit >= DAILY_TARGET?    ──► HALT  (target hit, protect gains)    │
│                                                                                     │
│   WebhookService checks is_halted() BEFORE placing any order.                      │
│   Existing open trades continue to be monitored — only NEW entries blocked.        │
│   Resets automatically at 9:15 AM next trading day.                                │
│   Can also be toggled manually via POST /killswitch                                 │
└─────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL TRADE DETECTION (Manual Trades)                    │
│                                                                                     │
│   MonitorService polls broker.get_positions() every 60s                            │
│                                                                                     │
│   Position found not in our DB?                                                     │
│       └── create Trade(source=EXTERNAL, state=OPEN)                                │
│       └── compute buy_price from avg cost                                           │
│       └── compute initial SL = buy_price * (1 - SL_PERCENT/100)                   │
│       └── trade_manager.register_trade()  ← same trailing SL rules apply          │
│                                                                                     │
│   Works for trades from Groww app, other devices, or manual punches.               │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Design Patterns

| Pattern | Where Used | Purpose |
|---------|-----------|---------|
| **Adapter** | `brokers/base.py` + `brokers/groww/adapter.py` | Unified broker interface — swap broker without touching engine |
| **Factory** | `brokers/factory.py` | Decouple broker creation from usage |
| **Observer** | `engine/price_observer.py` + `engine/trade_monitor.py` | React to price ticks per trade |
| **Strategy** | `engine/stoploss_strategy.py` | Plug-in SL logic (trailing, fixed, etc.) |
| **Command** | `engine/trade_command.py` | Encapsulate BUY/SELL, support undo |
| **Repository** | `repository/trade_repository.py` | Single access point for all DB operations |
| **State** | `engine/trade_state.py` | Explicit trade lifecycle, prevent invalid transitions |
| **Singleton** | `engine/trade_manager.py`, `brokers/groww/auth.py` | One instance, shared state |

---

## SOLID Principles

### S — Single Responsibility
Every class has exactly one reason to change.

| Class | Single Responsibility |
|-------|-----------------------|
| `GrowwAdapter` | Translate our generic order calls into Groww REST API calls |
| `GrowwFeed` | Manage the WebSocket connection and deliver price ticks |
| `TrailingStoplossStrategy` | Calculate SL levels — nothing else |
| `TradeMonitor` | Watch one trade and fire exit when SL is hit |
| `TradeRepository` | All DB reads/writes for trades — nothing else |
| `DailyRiskManager` | Track daily P&L and decide if trading should halt |
| `BuyCommand` / `SellCommand` | Encapsulate a single order action |

> Inspired by pykiteconnect splitting `KiteConnect` (REST) and `KiteTicker` (WebSocket) into two completely separate classes. We follow the same split: `GrowwAdapter` vs `GrowwFeed`.

---

### O — Open/Closed
Open for extension, closed for modification.

- `BrokerAdapter` is the stable abstraction. Adding Zerodha = new file, zero edits to existing code.
- `StoplossStrategy` is abstract. Adding ATR-based SL = new class, no changes to `TradeMonitor`.
- `BrokerFactory._registry` is a dict — extend by calling `register()`, never edit the factory itself.

---

### L — Liskov Substitution
Any `BrokerAdapter` subclass must be safely swappable for another.

`GrowwAdapter`, `ZerodhaAdapter`, `UpstoxAdapter` — all must:
- Return the same normalised dict shape from `get_positions()`
- Raise `BrokerOrderError` (never raw HTTP exceptions) on failure
- Accept the same arguments in `place_order()`

The engine never knows which broker is running. If swapping breaks something, the adapter violated LSP.

---

### I — Interface Segregation
Don't force a class to implement methods it doesn't use.

The `BrokerAdapter` is split into two focused interfaces:

```
BrokerRestAdapter        BrokerFeedAdapter
─────────────────        ─────────────────
place_order()            subscribe(symbols, callback)
cancel_order()           unsubscribe(symbols)
get_positions()          connect()
get_ltp()                disconnect()
```

`GrowwAdapter` implements `BrokerRestAdapter`.
`GrowwFeed` implements `BrokerFeedAdapter`.

Neither is forced to implement the other's methods.

> pykiteconnect gets this right: `KiteConnect` never handles WebSocket frames; `KiteTicker` never places orders.

---

### D — Dependency Inversion
High-level modules depend on abstractions, not concrete implementations.

```
WebhookService          depends on →   BrokerRestAdapter  (abstract)
TradeMonitor            depends on →   BrokerRestAdapter  (abstract)
MonitorService          depends on →   BrokerFeedAdapter  (abstract)
TradeManager            depends on →   BrokerRestAdapter + BrokerFeedAdapter
```

`GrowwAdapter` is only ever referenced in:
1. `brokers/factory.py` — to create the instance
2. `.env` — `BROKER=groww`

Nowhere else in the codebase imports `GrowwAdapter` directly.

---

### Exception Hierarchy (inspired by pykiteconnect's KiteException tree)

```
BrokerException                  ← base, always catch this at minimum
├── BrokerAuthError              ← token expired, login failed
├── BrokerOrderError             ← order rejected, invalid params
├── BrokerNetworkError           ← timeout, connection refused
└── BrokerDataError              ← malformed response from broker

AppException                     ← our app-level errors
├── InvalidSignalError           ← bad webhook payload or wrong secret
├── KillSwitchActiveError        ← new trade blocked by daily limits
├── TradeNotFoundError           ← trade ID not in DB
└── InvalidStateTransitionError  ← e.g. PENDING → CLOSED not allowed
```

Each exception carries `.code` (HTTP status) and `.message`. Same pattern as pykiteconnect.

---

### Constants (same pattern as pykiteconnect's class-level constants)

All broker constants live in `brokers/base.py` alongside the abstract class:

```python
class TransactionType(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    MARKET       = "MARKET"
    LIMIT        = "LIMIT"
    STOP_LOSS    = "SL"
    STOP_LOSS_MKT = "SL-M"

class Segment(str, Enum):
    CASH = "CASH"
    FNO  = "FNO"

class Product(str, Enum):
    MIS  = "MIS"    # Intraday
    CNC  = "CNC"    # Delivery
    NRML = "NRML"   # Carry forward (F&O)
```

Using `str, Enum` means they serialize to plain strings in JSON automatically — no extra conversion needed.

---

### Callback Pattern (from pykiteconnect's on_ticks / on_error style)

`GrowwFeed` uses the same optional callback approach:

```python
feed.on_connect   = None   # called when WS connects
feed.on_tick      = None   # called on every price update → (symbol, ltp)
feed.on_error     = None   # called on WS error
feed.on_close     = None   # called on disconnect
feed.on_reconnect = None   # called on each retry attempt
```

Set only what you need. Unset callbacks are silently skipped — no crashes.

---

### Reconnection Strategy (same as KiteTicker's exponential backoff)

`GrowwFeed` will implement:
- Ping every **2.5s**, expect pong within **5s**
- On disconnect: retry with backoff — `min(2^attempt, 60)` seconds
- On reconnect: automatically re-subscribe all previously subscribed symbols
- Max **50 retries** (configurable via env)

---

## Project Structure

```
monitering_service/
│
├── main.py                        # FastAPI app, lifespan startup/shutdown
├── config.py                      # All settings (env vars + capital + kill switch limits)
├── requirements.txt
├── .env.example
│
├── core/
│   ├── __init__.py
│   ├── database.py                # Async PostgreSQL engine (asyncpg), session factory
│   ├── exceptions.py              # Domain exceptions
│   └── logger.py                  # Structured logger
│
├── models/
│   ├── __init__.py
│   └── trade.py                   # SQLAlchemy ORM — trades + daily_stats tables
│
├── schemas/
│   ├── __init__.py
│   ├── webhook.py                 # SignalPayload (TradingView POST body)
│   └── trade.py                   # TradeRead (API response)
│
├── brokers/
│   ├── __init__.py
│   ├── base.py                    # BrokerAdapter abstract class      [ADAPTER]
│   ├── factory.py                 # BrokerFactory.create(name)        [FACTORY]
│   └── groww/
│       ├── __init__.py
│       ├── auth.py                # GrowwAuth — TOTP token flow (pyotp)
│       ├── adapter.py             # GrowwAdapter implements BrokerAdapter
│       └── feed.py                # GrowwFeed wrapper — WebSocket via growwapi
│
├── engine/
│   ├── __init__.py
│   ├── trade_state.py             # TradeState enum + StateMachine     [STATE]
│   ├── stoploss_strategy.py       # TrailingStoplossStrategy           [STRATEGY]
│   ├── trade_command.py           # BuyCommand, SellCommand            [COMMAND]
│   ├── price_observer.py          # PriceObserver ABC + TradeMonitor   [OBSERVER]
│   └── trade_manager.py           # TradeManager singleton             [SINGLETON]
│
├── risk/
│   ├── __init__.py
│   └── daily_risk_manager.py      # Kill switch — daily loss + target limits
│
├── repository/
│   ├── __init__.py
│   └── trade_repository.py        # All DB CRUD for trades + daily_stats [REPOSITORY]
│
├── services/
│   ├── __init__.py
│   ├── webhook_service.py         # Orchestrates: signal → kill switch → BuyCommand → monitor
│   └── monitor_service.py         # Background tasks: price feed + external scan loop
│
└── api/
    ├── __init__.py
    ├── webhook_router.py          # POST /webhook/signal
    ├── trades_router.py           # GET /trades  GET /trades/{id}  GET /trades/summary
    └── killswitch_router.py       # GET /killswitch  POST /killswitch
```

---

## How It Works

### 1. Webhook Flow

TradingView sends a POST to `/webhook/signal` with:

```json
{
  "secret": "your-secret",
  "symbol": "NIFTY",
  "direction": "BUY",
  "instrument_type": "index_option",
  "price": 22500.0
}
```

The service:
1. Validates the secret
2. Checks if kill switch is active — rejects if halted
3. Resolves the option contract from the underlying symbol
4. Calculates quantity: `floor(CAPITAL_INDEX_OPTION / option_ltp)`
5. Executes `BuyCommand` → broker places market order
6. Persists trade to DB with `state=OPEN`
7. Registers `TradeMonitor` — SL tracking begins immediately

---

### 2. Trailing SL Engine

```
Buy price: ₹100    SL_PERCENT: 5%    TRAILING_STEP: 5%

Initial SL = ₹95

Price → ₹105  (+5%)   →  SL trails to ₹100  (break-even protection)
Price → ₹110  (+10%)  →  SL trails to ₹105
Price → ₹115  (+15%)  →  SL trails to ₹110
Price → ₹104           →  SL stays at ₹110  (never moves down)
Price → ₹109  (≤ ₹110) →  EXIT IMMEDIATELY
```

The SL only moves up, never down. Each 5% gain band locks in the previous level as the new floor.

---

### 3. Kill Switch

Two automatic halt conditions — checked before every new trade entry:

| Condition | Trigger | Effect |
|-----------|---------|--------|
| **Daily Loss Limit** | Cumulative realized loss >= `DAILY_LOSS_LIMIT` | No new trades for the day |
| **Daily Target** | Cumulative realized profit >= `DAILY_TARGET` | No new trades for the day |

**Important:** The kill switch only blocks **new entries**. All currently open trades continue to be monitored and will exit normally via SL.

The counter resets automatically at 9:15 AM the next trading day.

Manual override via API:
```bash
# Check status
GET /killswitch

# Force halt (manual emergency stop)
POST /killswitch  {"active": true}

# Force resume
POST /killswitch  {"active": false}
```

---

### 4. External Trade Detection

Any trade punched manually — from the Groww app, another device, or a different system — is automatically detected and monitored.

```
Every 60 seconds:
  broker.get_positions()
  → diff against our open trades in DB
  → unknown position found?
      → create Trade(source=EXTERNAL)
      → set buy_price from position avg_cost
      → compute initial SL
      → register with TradeManager
      → same trailing SL rules now apply
```

---

### 5. Capital Configuration

Since Groww does not expose a balance API, capital is configured manually per instrument type in `.env`:

```
CAPITAL_INDEX_OPTION=50000    # ₹50,000 per index option trade
CAPITAL_STOCK_OPTION=25000    # ₹25,000 per stock option trade
```

Quantity is calculated as: `qty = floor(capital / ltp)`

---

## Groww API Reference

### Installation
```bash
pip install growwapi pyotp
```

### Authentication (TOTP — recommended)
```python
import pyotp
from growwapi import GrowwAPI

totp = pyotp.TOTP('YOUR_TOTP_SECRET').now()
access_token = GrowwAPI.get_access_token(api_key="YOUR_API_KEY", totp=totp)
groww = GrowwAPI(access_token)
```

### Place Order
```python
response = groww.place_order(
    trading_symbol="NIFTY24DEC21000CE",
    quantity=1,
    validity=groww.VALIDITY_DAY,
    exchange=groww.EXCHANGE_NSE,
    segment=groww.SEGMENT_FNO,          # FNO for options
    product=groww.PRODUCT_MIS,          # MIS for intraday
    order_type=groww.ORDER_TYPE_MARKET,
    transaction_type=groww.TRANSACTION_TYPE_BUY,
)
# { "groww_order_id": "GMK39038...", "order_status": "OPEN", ... }
```

### Get Positions
```python
positions = groww.get_positions_for_user()
# returns list of positions with avg_price, quantity, trading_symbol, segment
```

### Get LTP (up to 50 instruments)
```python
ltp = groww.get_ltp(
    segment=groww.SEGMENT_FNO,
    exchange_trading_symbols=("NSE_NIFTY24DEC21000CE",)
)
```

### WebSocket Price Feed
```python
from growwapi import GrowwFeed

feed = GrowwFeed(groww)

def on_tick(meta):
    data = feed.get_ltp()   # { "NSE_NIFTY24DEC21000CE": 250.5, ... }

feed.subscribe_ltp(["NSE_NIFTY24DEC21000CE"], on_data_received=on_tick)
feed.consume()   # blocking — run in a thread
```

### Rate Limits

| Type | Per Second | Per Minute |
|------|-----------|-----------|
| Orders | 10 | 250 |
| Live Data (LTP/OHLC) | 10 | 300 |
| Portfolio / Other | 20 | 500 |

---

## Adding a New Broker

1. Create `brokers/<broker_name>/adapter.py`
2. Implement all methods from `BrokerAdapter` (base.py)
3. Register in factory:

```python
# brokers/factory.py
BrokerFactory.register("zerodha", lambda: ZerodhaAdapter())
```

4. Set in `.env`:
```
BROKER=zerodha
```

Zero changes to the engine, services, or any other layer.

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
# Broker
BROKER=groww
GROWW_API_KEY=
GROWW_TOTP_SECRET=          # base32 secret from Groww API keys page

# Webhook
WEBHOOK_SECRET=your-secret-here

# Capital (manual — Groww has no balance API)
CAPITAL_INDEX_OPTION=50000
CAPITAL_STOCK_OPTION=25000

# Trailing SL
SL_PERCENT=5.0
TRAILING_STEP=5.0

# Kill Switch
DAILY_LOSS_LIMIT=5000       # Halt if day loss >= ₹5000
DAILY_TARGET=10000          # Halt if day profit >= ₹10000

# Database (local PostgreSQL)
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/trading_monitor

# External scan interval
EXTERNAL_SCAN_INTERVAL=60
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/webhook/signal` | TradingView signal entry point |
| `GET` | `/trades` | List all trades (filter by `?state=OPEN`) |
| `GET` | `/trades/{id}` | Single trade detail |
| `GET` | `/trades/summary` | Daily P&L, open count, capital deployed |
| `GET` | `/killswitch` | Get current kill switch status |
| `POST` | `/killswitch` | Manually activate or deactivate halt |

---

## Getting Started

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# fill in: GROWW_API_KEY, GROWW_TOTP_SECRET, DATABASE_URL, WEBHOOK_SECRET

# 3. Create PostgreSQL database
createdb trading_monitor

# 4. Run
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

On startup the service will:
- Run DB migrations (create tables if not exist)
- Authenticate with Groww via TOTP
- Load any `OPEN` trades from DB and resume monitoring them
- Start the WebSocket price feed (`GrowwFeed`)
- Start the 60s external trade scanner
- Begin accepting webhooks at `POST /webhook/signal`

---

## Trade Lifecycle

```
PENDING  →  order sent to broker, awaiting fill
OPEN     →  fill confirmed, SL engine active
SL_HIT   →  SL triggered, exit order sent
CLOSED   →  exit fill confirmed, P&L recorded
FAILED   →  order rejected by broker
```

Invalid transitions (e.g. PENDING → CLOSED) raise `InvalidStateTransitionError` and are logged.

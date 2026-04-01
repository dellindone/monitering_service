# Trading Monitoring Service

A production-grade, broker-agnostic trading monitoring service. Receives signals via webhook, punches trades through a broker adapter, tracks live prices via WebSocket, and enforces a trailing stop-loss engine — with daily kill switches and external trade detection.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Design Patterns](#design-patterns)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
  - [Webhook Flow](#1-webhook-flow)
  - [Trailing SL Engine](#2-trailing-sl-engine)
  - [Kill Switch](#3-kill-switch)
  - [External Trade Detection](#4-external-trade-detection)
  - [Capital Configuration](#5-capital-configuration)
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
│                         │    SQLite  (trades.db)   │                                │
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

## Project Structure

```
monitering_service/
│
├── main.py                        # FastAPI app, lifespan startup/shutdown
├── config.py                      # All settings (env vars + capital + kill switch limits)
├── requirements.txt
├── .env.example
├── trades.db                      # SQLite — auto-created on first run
│
├── core/
│   ├── database.py                # Async SQLite engine, session factory
│   ├── exceptions.py              # Domain exceptions
│   └── logger.py                  # Structured logger
│
├── models/
│   └── trade.py                   # Trade ORM model (SQLAlchemy)
│
├── schemas/
│   ├── webhook.py                 # SignalPayload (TradingView POST body)
│   └── trade.py                   # TradeRead (API response)
│
├── brokers/
│   ├── base.py                    # BrokerAdapter abstract class [ADAPTER]
│   ├── factory.py                 # BrokerFactory [FACTORY]
│   └── groww/
│       ├── auth.py                # GrowwAuth singleton — token management
│       ├── adapter.py             # GrowwAdapter implements BrokerAdapter
│       └── websocket.py          # GrowwPriceFeed — WebSocket live prices
│
├── engine/
│   ├── stoploss_strategy.py      # TrailingStoplossStrategy [STRATEGY]
│   ├── trade_command.py          # BuyCommand, SellCommand [COMMAND]
│   ├── trade_state.py            # TradeState enum + StateMachine [STATE]
│   ├── price_observer.py         # PriceObserver interface [OBSERVER]
│   └── trade_manager.py          # TradeManager singleton [SINGLETON]
│
├── risk/
│   └── daily_risk_manager.py     # Kill switch — daily loss/target limits
│
├── repository/
│   └── trade_repository.py       # All DB CRUD [REPOSITORY]
│
├── services/
│   ├── webhook_service.py        # Orchestrates webhook → trade flow
│   └── monitor_service.py        # Manages background tasks
│
└── api/
    ├── webhook_router.py         # POST /webhook/signal
    ├── trades_router.py          # GET /trades, GET /trades/{id}
    └── killswitch_router.py      # GET/POST /killswitch
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
GROWW_CLIENT_ID=
GROWW_CLIENT_SECRET=
GROWW_TOTP_SECRET=
GROWW_PIN=

# Webhook
WEBHOOK_SECRET=your-secret-here

# Capital (per trade, since Groww has no balance API)
CAPITAL_INDEX_OPTION=50000
CAPITAL_STOCK_OPTION=25000

# Trailing SL
SL_PERCENT=5.0
TRAILING_STEP=5.0

# Kill Switch
DAILY_LOSS_LIMIT=5000     # Halt if total day loss >= ₹5000
DAILY_TARGET=10000        # Halt if total day profit >= ₹10000

# Database
DATABASE_URL=sqlite+aiosqlite:///./trades.db
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
# Edit .env with your credentials and capital limits

# 3. Run
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The service will:
- Create `trades.db` on first run
- Authenticate with Groww
- Start the WebSocket price feed
- Start the 60-second external trade scanner
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

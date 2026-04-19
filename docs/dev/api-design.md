# Algorithmic Trading UI API Design

This design targets a FastAPI service that exposes local Binance candle data from
`file.db` and leaves room for strategy signals, backtests, watchlists, and paper
or live execution. The charting client is assumed to use TradingView Lightweight
Charts.

## Goals

- Serve OHLCV history in a shape Lightweight Charts can consume directly.
- Keep DuckDB reads simple, bounded, and cacheable.
- Make strategy overlays, markers, and backtest results first-class API objects.
- Separate read-only market-data APIs from mutating trading APIs.
- Generate FastAPI's OpenAPI schema without hand-maintaining duplicate models.

## Current Data Source

The local DuckDB file is `file.db`.

Current table:

```sql
binance_candles(
  symbol VARCHAR NOT NULL,
  interval VARCHAR NOT NULL,
  open_time TIMESTAMP NOT NULL,
  close_time TIMESTAMP NOT NULL,
  open DOUBLE NOT NULL,
  high DOUBLE NOT NULL,
  low DOUBLE NOT NULL,
  close DOUBLE NOT NULL,
  volume DOUBLE NOT NULL,
  quote_asset_volume DOUBLE NOT NULL,
  number_of_trades BIGINT NOT NULL,
  taker_buy_base_volume DOUBLE NOT NULL,
  taker_buy_quote_volume DOUBLE NOT NULL,
  primary key (symbol, interval, open_time)
)
```

Observed coverage on this checkout:

| Symbol | Interval | Earliest open | Latest open |
| --- | --- | --- | --- |
| ARBUSDT | 1d | 2024-01-01 09:00 | 2026-04-06 09:00 |
| BTCUSDT | 1d | 2017-08-17 09:00 | 2026-04-06 09:00 |
| ETHUSDT | 1d | 2017-09-01 09:00 | 2026-04-06 09:00 |
| OPUSDT | 1d | 2022-06-01 09:00 | 2026-04-06 09:00 |
| SOLUSDT | 1d | 2024-01-01 09:00 | 2026-04-06 09:00 |

Store timestamps internally as database timestamps, but expose API timestamps as
UTC Unix seconds for Lightweight Charts. The `open_time` values currently appear
at `09:00`, so the implementation should define the database timezone assumption
explicitly before returning them as Unix seconds. If these files were imported
from Binance daily klines, the intended candle boundary is normally UTC midnight.

## API Shape

Base path: `/api/v1`.

Read-only market data:

- `GET /health`
- `GET /markets`
- `GET /symbols`
- `GET /symbols/{symbol}`
- `GET /intervals?symbol=BTCUSDT`
- `GET /candles?symbol=BTCUSDT&interval=1d`
- `GET /candles/latest?symbol=BTCUSDT&interval=1d`
- `GET /ratios?base_symbol=BTCUSDT&quote_symbol=ETHUSDT&interval=1d`

Chart overlays:

- `GET /symbols/{symbol}/intervals/{interval}/indicators`
- `POST /indicators/preview`
- `GET /strategies`
- `GET /strategies/{strategy_id}/signals`

Backtesting:

- `POST /backtests`
- `GET /backtests/{backtest_id}`
- `GET /backtests/{backtest_id}/equity`
- `GET /backtests/{backtest_id}/trades`

Trading:

- `GET /accounts`
- `GET /accounts/{account_id}/positions`
- `POST /orders`
- `GET /orders`
- `DELETE /orders/{order_id}`

Trading endpoints should require authentication and should be disabled unless the
service is configured for paper or live trading. Market-data endpoints can remain
local-only and unauthenticated during development.

## Lightweight Charts Contract

Candles should be returned as:

```json
{
  "symbol": "BTCUSDT",
  "interval": "1d",
  "timezone": "UTC",
  "items": [
    {
      "time": 1502928000,
      "open": 4261.48,
      "high": 4485.39,
      "low": 4200.74,
      "close": 4285.08,
      "volume": 795.15
    }
  ],
  "page": {
    "limit": 1000,
    "next_cursor": "..."
  }
}
```

`time` is Unix seconds, not milliseconds. This matches Lightweight Charts'
`UTCTimestamp` format and avoids client-side conversion churn.

Markers and strategy signals should use the same `time` unit:

```json
{
  "items": [
    {
      "time": 1711929600,
      "position": "belowBar",
      "color": "#0ea5e9",
      "shape": "arrowUp",
      "text": "Long"
    }
  ]
}
```

Long-short pair ratios should be returned as synthetic OHLC candles:

```json
{
  "base_symbol": "BTCUSDT",
  "quote_symbol": "ETHUSDT",
  "interval": "1d",
  "timezone": "UTC",
  "items": [
    {
      "time": 1504224000,
      "open": 11.970281473564009,
      "high": 12.44635226278124,
      "low": 11.970281473564009,
      "close": 12.44635226278124,
      "base_close": 4834.91,
      "quote_close": 388.46
    }
  ],
  "page": {
    "limit": 500,
    "next_cursor": null
  }
}
```

`close` is `base_close / quote_close`, so `BTCUSDT/ETHUSDT` rising means BTC is
outperforming ETH over the selected interval.

## Query Semantics

`GET /candles?symbol=BTCUSDT&interval=1d`

Parameters:

- `symbol`: required symbol, e.g. `BTCUSDT`.
- `interval`: required candle interval, e.g. `1d`.
- `from`: inclusive lower bound as Unix seconds.
- `to`: exclusive upper bound as Unix seconds.
- `limit`: default `500`, maximum `5000`.
- `cursor`: opaque pagination token for older or newer slices.
- `order`: `asc` by default, `desc` for latest-first tables.
- `fields`: optional comma-separated set, e.g. `time,open,high,low,close,volume`.

Response ordering should match the `order` parameter. Chart clients should call
with `order=asc`.

DuckDB query sketch:

```sql
select
  epoch(open_time) as time,
  open,
  high,
  low,
  close,
  volume
from binance_candles
where symbol = ?
  and interval = ?
  and open_time >= to_timestamp(?)
  and open_time < to_timestamp(?)
order by open_time asc
limit ?;
```

Use parameter binding. Validate `symbol`, `interval`, and time range before
building the query. Do not interpolate user-provided strings into SQL.

The flat query-parameter endpoint is intentional for chart traffic. The UI builds
chart requests from state values such as symbol, interval, range, and overlays,
so representing all candle selectors as query parameters keeps client code and
DuckDB filters aligned. It also leaves room for later comparison endpoints such
as `GET /candles?symbols=BTCUSDT,ETHUSDT&interval=1d` without creating another
deep route family.

`GET /ratios?base_symbol=BTCUSDT&quote_symbol=ETHUSDT&interval=1d`

Parameters:

- `base_symbol`: required numerator symbol, commonly the long leg.
- `quote_symbol`: required denominator symbol, commonly the short leg.
- `interval`: required candle interval shared by both symbols.
- `from`, `to`, `limit`, and `order`: same semantics as `/candles`.

The ratio endpoint inner-joins candles by `open_time` and interval. Missing data
on either leg is omitted instead of forward-filled, which keeps the first version
simple and avoids inventing synthetic prices.

Ratio candle calculations:

- `open`: base open divided by quote open.
- `high`: the greater of ratio open and ratio close.
- `low`: the lesser of ratio open and ratio close.
- `close`: base close divided by quote close.

The backend intentionally does not calculate ratio wicks from `base.high /
quote.low` and `base.low / quote.high`. Those values are only theoretical bounds
when using daily OHLC because the highs and lows of two assets may occur at
different intraday times. Using them creates misleading oversized wicks.

## FastAPI Structure

Suggested package layout:

```text
src/
  api/
    app.py
    deps.py
    routers/
      health.py
      market_data.py
      indicators.py
      strategies.py
      backtests.py
      trading.py
    schemas/
      market_data.py
      indicators.py
      strategies.py
      backtests.py
      trading.py
  db/
    duckdb.py
```

Implementation notes:

- Open one DuckDB read-only connection per request or use a small connection
  provider dependency. DuckDB connections are not a general async connection pool.
- Keep database access in sync functions and let FastAPI run them in the default
  threadpool if routes are `async`.
- Add `BINANCE_DB_PATH=file.db` configuration.
- Add CORS only for known local UI origins.
- Use Pydantic response models so FastAPI generates the OpenAPI schema.

## Error Model

All errors should use the same shape:

```json
{
  "error": {
    "code": "symbol_not_found",
    "message": "Unknown symbol: DOGEUSDT",
    "details": {
      "symbol": "DOGEUSDT"
    }
  }
}
```

Common status codes:

- `400`: invalid interval, range, cursor, or order.
- `401`: missing authentication for trading endpoints.
- `403`: trading mode disabled or account not authorized.
- `404`: unknown symbol, strategy, account, backtest, or order.
- `409`: order cannot be cancelled in current state.
- `422`: FastAPI validation error.
- `500`: unexpected service error.

## Backtest Object Model

Backtests should be immutable once created:

- Request includes strategy id, symbol, interval, range, initial capital, fees,
  slippage, and strategy parameters.
- Response includes status, metrics, equity curve URL, trades URL, and optional
  chart marker URL.
- Long-running backtests can start as `queued` and move to `running`, `succeeded`,
  or `failed`.

This allows the UI to poll `GET /backtests/{backtest_id}` while keeping the
chart data and equity data independently fetchable.

## Trading Safety

Do not connect UI order buttons directly to a live exchange by default.

Recommended modes:

- `readonly`: market data, indicators, strategies, and backtests only.
- `paper`: accepts orders against a simulated account.
- `live`: requires explicit config, auth, account selection, and idempotency keys.

`POST /orders` should require an `Idempotency-Key` header to avoid duplicate
orders after browser retries.

## OpenAPI Contract

The initial hand-authored contract is in `api/openapi.yaml`. Once FastAPI models
exist, treat the generated schema as authoritative and use this file as the
implementation target or regression fixture.

# Chart UI User Manual

The chart UI is a React/Vite frontend for inspecting candles loaded into the
local DuckDB database. It talks to the FastAPI backend under `/api/v1`.

Use it after downloading and inserting Binance kline data into `file.db`.

## Requirements

- Python dependencies installed with `uv`.
- Node dependencies installed with `npm install`.
- A DuckDB database containing `binance_candles`, usually `file.db`.
- Backend running on `127.0.0.1:8000`.
- Frontend dev server running on `127.0.0.1:5173`.

Install dependencies:

```bash
uv sync --dev
npm install
```

## Start The Backend

Run:

```bash
uv run uvicorn main:app --host 127.0.0.1 --port 8000
```

Check backend health:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

Expected healthy response shape:

```json
{
  "status": "ok",
  "database": {
    "path": "file.db",
    "connected": true,
    "readonly": true
  }
}
```

If the backend cannot read `file.db`, the UI will not have market data.

## Start The Frontend

In another terminal, run:

```bash
npm run dev
```

Open:

```text
http://127.0.0.1:5173/
```

The Vite dev server proxies `/api` requests to the backend at
`http://127.0.0.1:8000` by default.

## Use A Different Backend

Set `VITE_PROXY_TARGET` when starting the frontend:

```bash
VITE_PROXY_TARGET=http://127.0.0.1:8001 npm run dev
```

You can also bypass the proxy by setting `VITE_API_BASE` at build/runtime:

```bash
VITE_API_BASE=http://127.0.0.1:8000/api/v1 npm run dev
```

## Mock Server Mode

The repo includes a mock-server path for the OpenAPI spec. Start the mock server:

```bash
npm run mock
```

Then start the frontend against the mock server:

```bash
VITE_PROXY_TARGET=http://127.0.0.1:4010 npm run dev
```

When `VITE_PROXY_TARGET` includes `4010`, the Vite proxy rewrites `/api/v1` to
the mock server root.

## Main Screen

The UI opens directly to the chart workspace.

Top area:

- Current symbol title, for example `BTCUSDT`.
- Status indicator:
  - green dot: last request succeeded,
  - red dot: request failed.
- Status text such as `Loading chart`, `Market data ready`, `Ratio ready`, or
  an HTTP error.

## Chart Modes

Use the mode switch above the controls:

- `Candles`: shows OHLC candles, volume bars, and strategy signal markers.
- `Ratio`: shows the ratio candle series for a numerator/denominator pair.

## Candle Mode

In `Candles` mode:

- `Symbol`: selected market symbol.
- `Interval`: one of `1d`, `4h`, `1h`, or `15m`.
- `Strategy`: selected strategy marker source.
- Range buttons:
  - `1M`: last 30 days,
  - `3M`: last 90 days,
  - `1Y`: last 365 days,
  - `All`: up to 5000 candles.

The chart displays:

- candlesticks,
- volume bars,
- strategy markers.

The metrics row shows:

- `Last`: latest close,
- `Session`: latest candle open-to-close percentage,
- `High`: latest candle high,
- `Low`: latest candle low,
- `Volume`: latest candle volume.

The lower `Signals` panel lists strategy markers with side, label, and date.

## Ratio Mode

In `Ratio` mode:

- `Numerator`: long-leg symbol.
- `Denominator`: short-leg symbol.
- `Interval`: shared interval.
- `Strategy`: still visible, but ratio mode displays ratio candles rather than
  signal markers.
- Range buttons work the same as candle mode.

The ratio endpoint joins candles by timestamp and computes ratio OHLC values.

The metrics row shows:

- `Ratio`: latest ratio close,
- `Range`: ratio change across the selected range,
- `Base Close`: latest numerator close,
- `Quote Close`: latest denominator close,
- `Pair`: selected numerator/denominator pair.

The lower `Pair` panel labels the numerator as the long leg and denominator as
the short leg.

## API Request Panel

The lower-right `API Request` panel shows the exact endpoint used for the
current chart.

Examples:

```text
/api/v1/candles?symbol=BTCUSDT&interval=1d&from=...&to=...&limit=1000&order=asc
```

```text
/api/v1/ratios?base_symbol=BTCUSDT&quote_symbol=ETHUSDT&interval=1d&from=...&to=...&limit=1000&order=asc
```

Use this panel when debugging backend responses or reproducing a request with
`curl`.

## Data Requirements

The symbol dropdown comes from:

```text
GET /api/v1/symbols
```

Only symbols already present in DuckDB appear in the UI.

The interval selector is currently fixed in the frontend:

```text
1d, 4h, 1h, 15m
```

If you select an interval that is not present for the symbol in DuckDB, the
backend returns an error and the UI shows `Request failed`.

## Verify Data Before Opening UI

Check available symbols and intervals:

```bash
uv run python -c "import duckdb; con=duckdb.connect('file.db'); print(con.execute(\"select symbol, list(distinct interval order by interval) from binance_candles group by symbol order by symbol limit 20\").fetchall())"
```

Check one candle series:

```bash
curl 'http://127.0.0.1:8000/api/v1/candles?symbol=BTCUSDT&interval=1d&limit=5&order=desc'
```

Check the symbol catalog:

```bash
curl http://127.0.0.1:8000/api/v1/symbols
```

## Troubleshooting

`Catalog load failed`

The frontend could not load `/api/v1/symbols` or `/api/v1/strategies`.

Check:

```bash
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/symbols
```

`Request failed`

The selected symbol, interval, range, or ratio request failed.

Common causes:

- backend is not running,
- `file.db` is missing,
- `binance_candles` table is empty,
- selected interval has no rows,
- ratio symbols do not overlap in time.

Symbol dropdown only shows `BTCUSDT`

That is the frontend fallback while the catalog is loading or after catalog
loading fails. Check the backend and DuckDB data.

The chart is empty

Check that the selected symbol and interval have rows:

```bash
uv run python -c "import duckdb; con=duckdb.connect('file.db'); print(con.execute(\"select count(*), min(open_time), max(open_time) from binance_candles where symbol='BTCUSDT' and interval='1d'\").fetchone())"
```

Ratio mode fails

Both symbols must have candles for the same interval and overlapping timestamps.
Check:

```bash
uv run python -c "import duckdb; con=duckdb.connect('file.db'); print(con.execute(\"select symbol, count(*), min(open_time), max(open_time) from binance_candles where symbol in ('BTCUSDT','ETHUSDT') and interval='1d' group by symbol\").fetchall())"
```

Frontend shows stale data

Refresh the browser after inserting new data. The UI fetches data when controls
change or the page loads; it does not currently stream live updates.

## Related Docs

- [Downloader guide](downloader.md)
- [All-tradable klines guide](all-tradable-klines.md)
- [API design notes](../dev/api-design.md)

# binance-data-checker
Say, you have downloaded some historical market data using [binance-bulk-downloader](https://github.com/aoki-h-jp/binance-bulk-downloader).
This package lets you check if there are missing files in the range.


# Features
* Check missing files in a date range 
* Convert CSV to Parquet format
* Add column names
* Fix timestamp inconsistency in the Binance data


# Downloader

See [docs/user/downloader.md](docs/user/downloader.md) for the downloader workflow,
configuration format, daily/monthly commands, output layout, and troubleshooting.

Check whether a downloader config only contains currently tradable Binance Spot
symbols:

```bash
uv run python examples/check_tradable_symbols.py --file configs/spot-1d.yaml
```

See [docs/user/tradable-symbols.md](docs/user/tradable-symbols.md) for listing tradable
symbols by quote asset, filtering cross/isolated margin pairs, requiring
borrowable assets, requiring market-order support, and validating downloader
configs.

See [docs/user/all-tradable-klines.md](docs/user/all-tradable-klines.md) for the
all-tradable downloader user manual.

See [docs/user/chart-ui.md](docs/user/chart-ui.md) for the chart UI user manual.

See [docs/dev/all-tradable-klines-design.md](docs/dev/all-tradable-klines-design.md)
for the all-tradable downloader architecture notes.


# Trading UI API

Run the FastAPI backend against the local DuckDB file:

```bash
uv run uvicorn main:app --host 127.0.0.1 --port 8000
```

Run the React chart UI:

```bash
npm run dev
```

The UI is available at `http://127.0.0.1:5173/` and proxies `/api/v1` to the
backend at `http://127.0.0.1:8000` by default.

The UI supports normal OHLCV candles and ratio candles for long-short pair views,
for example `BTCUSDT/ETHUSDT`. The backend endpoint is:

```bash
curl 'http://127.0.0.1:8000/api/v1/ratios?base_symbol=BTCUSDT&quote_symbol=ETHUSDT&interval=1d'
```

Run the Prism mock server instead of the backend:

```bash
npm run mock
VITE_PROXY_TARGET=http://127.0.0.1:4010 npm run dev
```

# Downloader User Guide

This project can download Binance historical kline ZIP files, extract them, and
load the CSV rows into `file.db` as DuckDB table `binance_candles`.

The downloader is incremental: it checks which candles are missing in DuckDB for
the configured symbols/date range, downloads the missing daily or full-month ZIP
files, then inserts the downloaded CSV data.

## Requirements

- Python environment managed by `uv`.
- A writable DuckDB database file, currently `file.db`.
- A YAML config file describing the market data range.
- Network access to `https://data.binance.vision`.

Install project dependencies:

```bash
uv sync --dev
```

## Config File

Example: `configs/spot-1d.yaml`

```yaml
asset: spot
data_type: klines
interval: 1d
symbols:
  - BTCUSDT
  - ETHUSDT
  - ARBUSDT
  - OPUSDT
  - SOLUSDT
start_date: 2024-01-01
end_date: 2026-04-06
destination_dir: ./data
```

Fields:

- `asset`: Binance data asset group. Currently expected to be `spot`.
- `data_type`: Binance data type. For candles, use `klines`.
- `interval`: Binance kline interval, for example `1d`, `1h`, `5m`, or `1m`.
- `symbols`: list of symbols to download.
- `start_date`: inclusive start date for missing-data checks.
- `end_date`: inclusive end date for missing-data checks.
- `destination_dir`: local root directory for downloaded and extracted files.

The downloader writes Binance paths under `destination_dir`. For the config
above, BTC daily ZIPs are stored under:

```text
data/spot/daily/klines/BTCUSDT/1d/
```

## Run Daily Downloads

Daily mode downloads one ZIP per missing day:

```bash
uv run python examples/run_download.py --file configs/spot-1d.yaml --freq daily
```

Use daily mode when you are filling recent gaps or downloading short ranges.

## Check Tradable Symbols

For the full symbol-listing workflow, see
[tradable-symbols.md](tradable-symbols.md).

Before downloading a new config, check that the requested symbols are currently
tradable on Binance Spot:

```bash
uv run python examples/check_tradable_symbols.py --file configs/spot-1d.yaml
```

The command calls Binance Spot `GET /api/v3/exchangeInfo` and treats symbols
with `status: TRADING` as tradable. If any configured symbol is missing or not in
`TRADING` status, the command exits with status code `1`.

List all currently tradable USDT spot symbols:

```bash
uv run python examples/check_tradable_symbols.py --quote USDT
```

Only list pairs that support market orders:

```bash
uv run python examples/check_tradable_symbols.py --quote USDT --require-market-order
```

Limit output while exploring:

```bash
uv run python examples/check_tradable_symbols.py --quote USDT --limit 20
```

Important distinction: `exchangeInfo` tells you what is currently tradable on
the live Binance Spot exchange. Historical files on `data.binance.vision` can
include older symbols, and not every historical symbol is tradable today.

## Run Monthly Downloads

Monthly mode downloads one ZIP for each fully missing calendar month:

```bash
uv run python examples/run_download.py --file configs/spot-1d.yaml --freq monthly
```

Use monthly mode for initial backfills. It only downloads months where every day
in that month is missing from DuckDB for the symbol and interval.

## Download All Tradable Symbols

To resolve all currently tradable Binance Spot symbols and download klines for
them, use `symbol_source: tradable` instead of a fixed `symbols` list:

```yaml
asset: spot
data_type: klines
interval: 1d
symbol_source: tradable
quote_asset: USDT
require_market_order: true
margin: none
require_borrowable:
start_date: 2024-01-01
end_date: 2026-04-06
destination_dir: ./data
db_path: file.db
batch_size: 25
download_concurrency: 10
missing_frequency: monthly
```

Run a dry-run first to inspect symbol and URL counts:

```bash
uv run python examples/download_tradable_klines.py --file configs/spot-all-usdt-1d.yaml --dry-run
```

Run a small smoke test:

```bash
uv run python examples/download_tradable_klines.py --file configs/spot-all-usdt-1d.yaml --limit-symbols 3
```

The command writes a JSON manifest under `data/manifests/` with the resolved
symbols, batch progress, URL counts, download categories, and final status.
Historical `404` responses from `data.binance.vision` are treated as
`missing_remote` because currently tradable symbols may not have existed for the
whole requested date range.

For the full operational manual, see
[all-tradable-klines.md](all-tradable-klines.md).

## What The Command Does

`examples/run_download.py` performs these steps:

1. Reads the YAML config.
2. Opens `file.db`.
3. Computes missing days or fully missing months from `binance_candles`.
4. Builds Binance download URLs.
5. Downloads ZIP files concurrently with retry handling.
6. Extracts ZIP files safely.
7. Inserts CSV rows into DuckDB with `insert or ignore`.

The target DuckDB table is:

```sql
binance_candles(
  symbol,
  interval,
  open_time,
  close_time,
  open,
  high,
  low,
  close,
  volume,
  quote_asset_volume,
  number_of_trades,
  taker_buy_base_volume,
  taker_buy_quote_volume
)
```

The table has a primary key on `(symbol, interval, open_time)`, so rerunning the
same download is safe. Existing candles are ignored on insert.

## Error Handling

Downloads fail loudly. If any URL still fails after retries, the command raises
`DownloadError` with a summary of failed URLs and stops before insertion.

Common causes:

- `404`: Binance does not have that symbol/interval/date file.
- Network timeout: retry the command.
- Permission error: check `destination_dir` permissions.
- Bad ZIP path: extraction is blocked if a ZIP contains unsafe paths.

Partial files are written as `*.part` and then moved into place only after a
successful download.

## Programmatic Use

You can use the downloader from Python:

```python
import asyncio

from src.downloader import concurrent_download

urls = [
    "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1d/BTCUSDT-1d-2026-04-06.zip"
]

results = asyncio.run(
    concurrent_download(
        urls,
        n=10,
        destination_dir="./data",
        retries=2,
    )
)

for result in results:
    print(result.path)
```

Arguments:

- `urls`: iterable of Binance data URLs.
- `n`: max concurrent downloads.
- `destination_dir`: local output root.
- `retries`: retry count after the first attempt.

## Verify Data

Check available data in DuckDB:

```bash
uv run python -c "import duckdb; con=duckdb.connect('file.db'); print(con.execute(\"select symbol, interval, count(*), min(open_time), max(open_time) from binance_candles group by 1,2 order by 1,2\").fetchall())"
```

Start the API and inspect data from the UI:

```bash
uv run uvicorn main:app --host 127.0.0.1 --port 8000
npm run dev
```

Then open:

```text
http://127.0.0.1:5173/
```

## Notes

- The downloader currently uses the local database path `file.db` in
  `examples/run_download.py`.
- Daily and monthly modes both load data into the same `binance_candles` table.
- Safe ZIP extraction rejects absolute paths and `..` traversal paths before
  extracting.

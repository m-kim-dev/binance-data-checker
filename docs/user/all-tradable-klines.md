# All-Tradable Klines User Manual

Use this workflow when you want to download Binance Spot kline history for every
symbol Binance currently reports as tradable.

The command resolves the live symbol list from Binance, filters it according to
your config, computes missing files from DuckDB, downloads historical ZIP files
from `data.binance.vision`, extracts CSVs, and inserts rows into
`binance_candles`.

## Quick Start

Install dependencies:

```bash
uv sync --dev
```

Inspect the example config:

```bash
configs/spot-all-usdt-1d.yaml
```

Run a dry-run first:

```bash
uv run python examples/download_tradable_klines.py \
  --file configs/spot-all-usdt-1d.yaml \
  --dry-run
```

Run a small live smoke test:

```bash
uv run python examples/download_tradable_klines.py \
  --file configs/spot-all-usdt-1d.yaml \
  --limit-symbols 3
```

Run the full download:

```bash
uv run python examples/download_tradable_klines.py \
  --file configs/spot-all-usdt-1d.yaml
```

## Example Config

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

## Config Fields

- `asset`: Binance asset group. Currently only `spot` is supported.
- `data_type`: Binance data type. Currently only `klines` is supported.
- `interval`: kline interval, for example `1d`, `4h`, `1h`, `15m`, or `1m`.
- `symbol_source`: use `tradable` to resolve symbols from Binance
  `exchangeInfo`.
- `quote_asset`: optional quote filter, for example `USDT`, `BTC`, or `FDUSD`.
- `require_market_order`: when `true`, keeps only symbols that support MARKET
  orders.
- `margin`: one of `none`, `cross`, `isolated`, or `any`.
- `require_borrowable`: optional margin borrowability filter. Use `base`,
  `quote`, `both`, or `any`.
- `start_date`: inclusive start date for missing-data checks.
- `end_date`: inclusive end date for missing-data checks.
- `destination_dir`: local root for downloaded ZIPs, extracted CSVs, and
  manifests.
- `db_path`: DuckDB database path.
- `batch_size`: number of symbols processed per batch.
- `download_concurrency`: maximum concurrent downloads.
- `missing_frequency`: `monthly` or `daily`.

Use exactly one of these config styles:

- `symbols: [...]` for a fixed symbol list.
- `symbol_source: tradable` for live all-tradable symbol resolution.

Do not use both in the same config.

## Command Options

```bash
uv run python examples/download_tradable_klines.py --help
```

Options:

- `--file`: required YAML config path.
- `--freq daily|monthly`: override `missing_frequency`.
- `--dry-run`: resolve symbols and compute URL counts without downloading.
- `--limit-symbols N`: only process the first `N` resolved symbols. Useful for
  smoke tests.
- `--force`: redownload ZIPs even if the destination file already exists.
- `--continue-on-error`: keep processing later batches after failed URLs.
- `--api-key`: Binance API key for margin metadata endpoints. Defaults to
  `BINANCE_API_KEY`.

## Recommended Operating Flow

1. Start with `missing_frequency: monthly` for initial backfills.
2. Run `--dry-run` and inspect symbol and URL counts.
3. Run `--limit-symbols 3` for a small live test.
4. Run the full monthly download.
5. Use `missing_frequency: daily` later to fill recent gaps.

Monthly mode downloads one ZIP per fully missing calendar month. Daily mode
downloads one ZIP per missing day.

## Output Layout

Downloaded files follow the Binance path under `destination_dir`:

```text
data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2026-03.zip
data/spot/daily/klines/BTCUSDT/1d/BTCUSDT-1d-2026-04-06.zip
```

ZIP files are extracted into the same symbol/interval directory before CSV rows
are inserted into DuckDB.

Partial downloads use `*.part` files and are moved into place only after the
download succeeds.

## DuckDB Table

Rows are loaded into `binance_candles`:

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

The table primary key is `(symbol, interval, open_time)`. Rerunning the command
is safe because inserts use `insert or ignore`.

## Manifests

Every run writes a manifest under:

```text
data/manifests/
```

The command prints the exact manifest path at the end:

```text
run_id: 20260419T000000Z-spot-klines-1d
symbols: 420
urls: 5040
failed: 0
manifest: data/manifests/20260419T000000Z-spot-klines-1d.json
```

The manifest includes:

- config values used for the run,
- symbol resolution source and filters,
- resolved symbols,
- batch status,
- URL count per batch,
- downloaded, skipped, missing-remote, and failed counts,
- final status.

## Download Categories

Each URL is categorized as:

- `downloaded`: HTTP 200 and ZIP file written.
- `skipped`: local ZIP already exists and `--force` was not used.
- `missing_remote`: Binance returned `404`; this is expected for dates before a
  currently tradable symbol existed.
- `failed`: network error or non-expected HTTP failure after retries.

The all-tradable command treats historical `404` responses as `missing_remote`,
not as hard failures. This matters because a symbol can be tradable today while
not having files for older months in your configured date range.

## Margin Filters

No API key is needed for basic Spot tradability:

```yaml
symbol_source: tradable
quote_asset: USDT
margin: none
```

Cross-margin filtering can work from Spot metadata without a key:

```yaml
margin: cross
```

Isolated-margin and borrowability filters require an API key:

```bash
BINANCE_API_KEY=your_key uv run python examples/download_tradable_klines.py \
  --file configs/spot-all-usdt-1d.yaml
```

You can also pass the key explicitly:

```bash
uv run python examples/download_tradable_klines.py \
  --file configs/spot-all-usdt-1d.yaml \
  --api-key your_key
```

The key is used only as the `X-MBX-APIKEY` header for Binance metadata
endpoints. The command does not use your secret key.

## Verify Data

Check loaded rows:

```bash
uv run python -c "import duckdb; con=duckdb.connect('file.db'); print(con.execute(\"select symbol, interval, count(*), min(open_time), max(open_time) from binance_candles group by 1,2 order by 1,2\").fetchall())"
```

Count symbols:

```bash
uv run python -c "import duckdb; con=duckdb.connect('file.db'); print(con.execute(\"select count(distinct symbol) from binance_candles\").fetchone())"
```

Inspect one symbol:

```bash
uv run python -c "import duckdb; con=duckdb.connect('file.db'); print(con.execute(\"select * from binance_candles where symbol = 'BTCUSDT' order by open_time desc limit 5\").fetchall())"
```

## Troubleshooting

`Config requires symbols or symbol_source`

Add either `symbols:` or `symbol_source: tradable` to the YAML config.

`Use either symbols or symbol_source, not both`

Remove one of those fields. Fixed-symbol downloads use `symbols`; all-tradable
downloads use `symbol_source: tradable`.

`margin isolated/any requires a Binance API key`

Set `BINANCE_API_KEY` or pass `--api-key`.

Many `missing_remote` results

This is normal when your `start_date` is older than many symbols. Narrow the
date range or accept the manifest as the record of unavailable files.

The run is too large

Use `--dry-run`, reduce the date range, use `--limit-symbols` for testing, or
lower `batch_size`. For high-frequency intervals such as `1m`, start with a
small symbol limit.

Existing files are not redownloaded

This is the default. Use `--force` to redownload local ZIPs.

## Related Docs

- [Downloader guide](downloader.md)
- [Tradable symbols guide](tradable-symbols.md)
- [All-tradable design](../dev/all-tradable-klines-design.md)

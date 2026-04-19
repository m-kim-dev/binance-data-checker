# Download Klines For All Tradable Symbols

This design extends the existing downloader so it can backfill Binance Spot
klines for every currently tradable symbol, while keeping the current
incremental DuckDB workflow.

No implementation is included here. The goal is to define the architecture and
the minimal changes needed before coding.

## Current System

The downloader already has the main primitives:

- `src.binance_symbols` fetches Binance Spot `exchangeInfo`, parses symbols,
  and filters `status == "TRADING"` symbols by quote asset, market-order
  support, margin availability, and borrowability.
- `src.filelist_generator.build_datelist` checks DuckDB table
  `binance_candles` and returns missing daily dates or fully missing months for
  configured symbols.
- `src.url_builder.build_urls` builds `data.binance.vision` kline ZIP URLs from
  the missing-date structure.
- `src.downloader.concurrent_download` downloads URLs concurrently with retries,
  atomic `*.part` writes, and aggregate failure reporting.
- `src.data_inserter.insert_from_zip` extracts downloaded ZIPs safely and loads
  CSV rows into DuckDB with `insert or ignore`.
- `examples/run_download.py` wires those pieces together for a YAML config with
  an explicit `symbols` list.

The missing capability is orchestration: resolving a large live symbol universe,
persisting that run's symbol set, batching work, tolerating expected historical
404s, and reporting progress.

## Goals

- Download klines for all currently tradable Binance Spot symbols.
- Preserve the existing DuckDB target table, primary key, and idempotent insert
  behavior.
- Support filters such as quote asset, market-order support, and margin-related
  filters using the existing `src.binance_symbols` functions.
- Scale to hundreds or thousands of symbols without creating one huge,
  hard-to-resume task.
- Keep daily and monthly modes. Use monthly mode for initial backfills and daily
  mode for recent gaps.
- Make reruns safe: already inserted candles and already downloaded files should
  not create duplicate rows.

## Non-Goals

- Do not replace DuckDB or change the `binance_candles` schema for the first
  implementation.
- Do not use Binance trading API kline endpoints for historical bulk data. The
  bulk source remains `https://data.binance.vision`.
- Do not treat "currently tradable" as the same as "historically existed for the
  whole requested date range". Newer symbols will legitimately produce missing
  historical files before their listing date.
- Do not implement symbol delisting history in the first version.

## Proposed Workflow

1. Load a downloader config.
2. Resolve symbols:
   - If `symbols` is present, use the existing explicit list behavior.
   - If `symbol_source: tradable` is configured, fetch `exchangeInfo`, parse it,
     and filter it through `tradable_symbols`.
3. Persist a run manifest containing:
   - resolved symbols,
   - filters used,
   - Binance metadata fetch timestamp,
   - interval/date range/frequency,
   - database path and destination directory.
4. Open DuckDB and ensure `binance_candles` exists before missing-data checks.
5. Process symbols in batches:
   - compute missing months or days for the batch,
   - build URLs,
   - skip URLs whose final ZIP already exists unless `--force` is set,
   - download with bounded concurrency,
   - insert ZIP contents into DuckDB for that batch,
   - write batch status to the manifest.
6. Emit a final summary:
   - symbol count,
   - attempted URLs,
   - downloaded files,
   - skipped existing files,
   - inserted row count if available,
   - failed URLs grouped by HTTP status or exception.

## Config Shape

Keep the existing config valid:

```yaml
asset: spot
data_type: klines
interval: 1d
symbols:
  - BTCUSDT
  - ETHUSDT
start_date: 2024-01-01
end_date: 2026-04-06
destination_dir: ./data
```

Add an optional symbol source for all-tradable downloads:

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

Recommended validation rules:

- Exactly one of `symbols` or `symbol_source: tradable` should be used.
- `asset` should initially be `spot`.
- `data_type` should initially be `klines`.
- `missing_frequency` should be `monthly` or `daily`.
- `batch_size` and `download_concurrency` must be positive integers.
- Margin and borrowability filters should reuse the accepted values from
  `examples/check_tradable_symbols.py`.

## Module Design

### `src.paths`

Extend `Config` to include optional fields for symbol sourcing and run control.
The current dataclass can stay simple, but it should validate mutually exclusive
`symbols` and `symbol_source`.

Suggested fields:

- `symbols: list[str] | None`
- `symbol_source: str | None`
- `quote_asset: str | None`
- `require_market_order: bool = False`
- `margin: str = "none"`
- `require_borrowable: str | None = None`
- `db_path: str = "file.db"`
- `batch_size: int = 25`
- `download_concurrency: int = 10`
- `missing_frequency: str | None = None`

### New `src.symbol_resolver`

Keep symbol-resolution orchestration separate from downloader IO.

Responsibilities:

- Accept `Config` and optional API key.
- Return a sorted list of `BinanceSymbol` or symbol strings.
- Use `fetch_exchange_info`, `parse_symbols`, and `tradable_symbols`.
- Fetch margin metadata only when requested by the config.
- Provide a small summary object with counts and filters.

This keeps `src.binance_symbols` as a low-level API/parsing/filtering module.

### `src.filelist_generator`

The existing SQL is appropriate for batch work. Two improvements should be made
before large runs:

- Ensure `binance_candles` exists before running the missing-days macro.
- Accept a sequence of symbols directly or operate on a config copy per batch.

### `src.url_builder`

Keep the current URL format, but make the API clearer before scaling:

- Avoid naming a parameter `dict`.
- Use explicit types.
- Validate `freq` against `daily` and `monthly`.
- Use a small URL descriptor dataclass if progress reporting needs symbol,
  interval, frequency, and date without reparsing the URL.

### `src.downloader`

The downloader is already usable. For all-symbol scale, add optional behavior:

- `skip_existing=True`, using `destination_path(url, destination_dir).exists()`.
- Structured result status such as `downloaded`, `skipped`, or `failed`.
- Optional `expected_missing_statuses={404}` for historical files that do not
  exist before a symbol listing date. This should be reported separately from
  hard failures.
- Progress callback or periodic logging.

### `src.data_inserter`

The inserter can remain idempotent. For batch orchestration, it should return a
summary:

- ZIPs extracted,
- CSV files matched,
- rows inserted if DuckDB exposes the count reliably,
- symbols processed.

Also move `CREATE_TABLE_SQL` execution before missing-date calculation so a new
database can start cleanly.

### New `src.klines_orchestrator`

This should become the main application service for download runs.

Responsibilities:

- Load/receive config.
- Resolve symbols.
- Create a run manifest.
- Iterate batches.
- Build missing-date lists and URLs.
- Call `concurrent_download`.
- Call `insert_from_zip`.
- Persist progress after each batch.
- Return a final run summary.

This prevents `examples/run_download.py` from becoming a large application.

## Manifest

Write a JSON manifest under:

```text
<destination_dir>/manifests/<run_id>.json
```

Use UTC timestamps and make it append/update after each batch. Suggested shape:

```json
{
  "run_id": "20260419T000000Z-spot-klines-1d",
  "started_at": "2026-04-19T00:00:00Z",
  "config": {
    "asset": "spot",
    "data_type": "klines",
    "interval": "1d",
    "start_date": "2024-01-01",
    "end_date": "2026-04-06",
    "quote_asset": "USDT"
  },
  "symbol_count": 420,
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "batches": [
    {
      "index": 0,
      "symbols": ["BTCUSDT", "ETHUSDT"],
      "url_count": 48,
      "downloaded": 48,
      "skipped": 0,
      "missing_remote": 0,
      "failed": 0,
      "status": "complete"
    }
  ],
  "status": "running"
}
```

The manifest is useful for auditability and for implementing resume later.

## Error Handling Policy

Large Binance bulk downloads need different failure classes:

- `skipped_existing`: local ZIP already exists.
- `downloaded`: HTTP 200 and file written atomically.
- `missing_remote`: HTTP 404 for a historical file. This is common for dates
  before a symbol was listed.
- `retryable_failure`: timeout, connection reset, or HTTP 5xx after retries.
- `hard_failure`: unsafe path, invalid config, database error, or repeated 4xx
  other than expected 404.

Default behavior should be:

- Continue through expected 404s and report them.
- Stop the current run on hard failures.
- Stop on retryable failures after retries unless `--continue-on-error` is set.

## Batching Strategy

Batch by symbols rather than by URLs. A symbol batch keeps DuckDB checks,
downloads, extraction, and insertion scoped to a readable unit.

Defaults:

- `batch_size: 25`
- `download_concurrency: 10`
- monthly mode for initial backfill
- daily mode for recent updates

For very large minute-level backfills, reduce `batch_size` before increasing
concurrency. The bottleneck can move from network to filesystem and DuckDB CSV
loading.

## Command-Line Shape

Keep the existing example command working:

```bash
uv run python examples/run_download.py --file configs/spot-1d.yaml --freq daily
```

Add a new script or CLI entry for the all-tradable workflow:

```bash
uv run python examples/download_tradable_klines.py --file configs/spot-all-usdt-1d.yaml
```

Useful options:

- `--freq daily|monthly` overrides `missing_frequency`.
- `--dry-run` resolves symbols and prints URL counts without downloading.
- `--limit-symbols N` for smoke tests.
- `--force` redownloads existing ZIPs.
- `--continue-on-error` completes remaining batches after failed URLs.

## Testing Plan

Unit tests:

- Config validation rejects both `symbols` and `symbol_source`.
- Symbol resolver returns sorted tradable symbols with quote and market-order
  filters.
- Symbol resolver fetches margin metadata only when margin or borrowability
  filters need it.
- URL builder produces daily and monthly URLs for multiple symbols.
- Downloader skip-existing behavior returns skipped results without network IO.
- Expected 404s are categorized separately from hard failures.
- Orchestrator batches symbols deterministically and writes manifest progress.

Integration tests:

- Run a dry-run all-tradable config with a fake `exchangeInfo`.
- Use a temporary DuckDB database and local fake downloader responses.
- Verify reruns are idempotent and do not duplicate rows.

Manual smoke test:

```bash
uv run python examples/download_tradable_klines.py \
  --file configs/spot-all-usdt-1d.yaml \
  --freq monthly \
  --limit-symbols 3 \
  --dry-run
```

Then run the same command without `--dry-run` for a small date range.

## Implementation Order

1. Extend and validate `Config`.
2. Add `src.symbol_resolver`.
3. Refactor URL builder names and validation without changing output.
4. Add downloader skip-existing and result categorization.
5. Add `src.klines_orchestrator` with dry-run support.
6. Add manifest writing.
7. Add `examples/download_tradable_klines.py`.
8. Add tests around resolver, downloader categorization, and orchestration.
9. Document the new config and command in `docs/user/downloader.md`.

## Main Risks

- Binance live tradability does not imply historical file availability for the
  requested date range. Treat 404s as expected historical gaps, not necessarily
  run failures.
- A new DuckDB database currently needs the table created before missing-data
  SQL runs.
- Very broad configs can produce many thousands of URLs. Dry-run and batching
  should be available before real downloads.
- Margin and borrowability filters can require a Binance API key. The resolver
  should fail early with a clear message when the selected filters need one.

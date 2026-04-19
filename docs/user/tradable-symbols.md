# Tradable Binance Symbols User Guide

Use this guide when you want to list symbols that are currently tradable on
Binance Spot, or validate that a downloader config only contains symbols Binance
currently reports as tradable. You can also filter for margin pairs and
borrowable margin assets.

The command uses Binance Spot `GET /api/v3/exchangeInfo`. A symbol is treated as
tradable when Binance returns `status: TRADING`.

Margin filters also use:

- `GET /sapi/v1/margin/allPairs` for cross margin pairs.
- `GET /sapi/v1/margin/isolated/allPairs` for isolated margin pairs.
- `GET /sapi/v1/margin/allAssets` for borrowable margin assets.

## Requirements

- Python environment managed by `uv`.
- Network access to `https://api.binance.com`.
- No Binance API key is needed for Spot tradability or basic cross-margin
  filtering.
- A Binance API key is needed for isolated-margin and borrowability filters. The
  command only sends the key as `X-MBX-APIKEY` for market metadata endpoints; it
  does not need your secret key.
- Project dependencies installed:

```bash
uv sync --dev
```

## List All Tradable Spot Symbols

Run:

```bash
uv run python examples/check_tradable_symbols.py
```

Output format:

```text
BTCUSDT,BTC,USDT,TRADING
ETHUSDT,ETH,USDT,TRADING
```

Each row is:

```text
symbol,base_asset,quote_asset,status
```

## List Tradable Symbols By Quote Asset

Most downloader configs use one quote asset, for example USDT. To list only
currently tradable USDT pairs:

```bash
uv run python examples/check_tradable_symbols.py --quote USDT
```

Other examples:

```bash
uv run python examples/check_tradable_symbols.py --quote BTC
uv run python examples/check_tradable_symbols.py --quote FDUSD
```

The quote filter is case-insensitive.

## Require Market Order Support

If your workflow needs market orders, add `--require-market-order`:

```bash
uv run python examples/check_tradable_symbols.py --quote USDT --require-market-order
```

This keeps only symbols where Binance includes `MARKET` in the symbol's allowed
order types.

## Filter Margin-Tradable Symbols

Use `--margin` when you only want symbols available for margin trading.

Cross margin:

```bash
uv run python examples/check_tradable_symbols.py --quote USDT --margin cross
```

This works without `BINANCE_API_KEY`. In no-key mode, the command uses Spot
`exchangeInfo` fields:

```text
isMarginTradingAllowed == true
```

or:

```text
"MARGIN" in permissions
```

Isolated margin:

```bash
BINANCE_API_KEY=your_key uv run python examples/check_tradable_symbols.py --quote USDT --margin isolated
```

Either cross or isolated margin:

```bash
BINANCE_API_KEY=your_key uv run python examples/check_tradable_symbols.py --quote USDT --margin any
```

`--margin cross` works without an API key by checking Spot `exchangeInfo`
metadata. If you also pass an API key, the command additionally checks Binance's
cross-margin pair endpoint. `--margin isolated` checks the isolated-margin pair
endpoint because Spot `exchangeInfo` does not fully describe isolated-margin
availability.

Binance currently requires an API key header for the margin metadata endpoints.
You can pass it either way:

```bash
uv run python examples/check_tradable_symbols.py --quote USDT --margin any --api-key your_key
BINANCE_API_KEY=your_key uv run python examples/check_tradable_symbols.py --quote USDT --margin any
```

Summary:

```text
No API key needed:
  --quote USDT
  --quote USDT --margin cross

API key needed:
  --margin isolated
  --margin any
  --require-borrowable base|quote|both|any
```

## Require Borrowable Assets

Margin availability means the pair can be traded on margin. Borrowability answers
a different question: can the needed asset currently be borrowed?

For a short setup, you usually care whether the base asset is borrowable. For
example, shorting `BTCUSDT` requires borrowing BTC:

```bash
BINANCE_API_KEY=your_key uv run python examples/check_tradable_symbols.py --quote USDT --margin any --require-borrowable base
```

For a margin buy setup, you usually care whether the quote asset is borrowable.
Buying `BTCUSDT` with borrowed quote requires borrowing USDT:

```bash
BINANCE_API_KEY=your_key uv run python examples/check_tradable_symbols.py --quote USDT --margin any --require-borrowable quote
```

You can also require both assets, or either asset:

```bash
BINANCE_API_KEY=your_key uv run python examples/check_tradable_symbols.py --quote USDT --margin any --require-borrowable both
BINANCE_API_KEY=your_key uv run python examples/check_tradable_symbols.py --quote USDT --margin any --require-borrowable any
```

If you pass `--require-borrowable` without a value, it defaults to `base`:

```bash
BINANCE_API_KEY=your_key uv run python examples/check_tradable_symbols.py --quote USDT --margin any --require-borrowable
```

## Limit Output While Exploring

Use `--limit` when you only want to inspect a few rows:

```bash
uv run python examples/check_tradable_symbols.py --quote USDT --limit 20
```

`--limit` only affects printed list output. It does not change Binance's
definition of tradability.

## Validate A Downloader Config

Before downloading data, validate the symbols in a YAML config:

```bash
uv run python examples/check_tradable_symbols.py --file configs/spot-1d.yaml
```

Validate that configured symbols are currently margin tradable and have
borrowable base assets:

```bash
BINANCE_API_KEY=your_key uv run python examples/check_tradable_symbols.py --file configs/spot-1d.yaml --margin any --require-borrowable base
```

Example success output:

```text
tradable: 5
OK BTCUSDT BTC/USDT
OK ETHUSDT ETH/USDT
OK ARBUSDT ARB/USDT
OK OPUSDT OP/USDT
OK SOLUSDT SOL/USDT
```

If every configured symbol is currently tradable, the command exits with status
code `0`.

If a symbol is missing or no longer in `TRADING` status, the command prints the
problem and exits with status code `1`. The command also exits with status code
`1` when a symbol is tradable on Spot but filtered out by the requested margin or
borrowability rules:

```text
tradable: 1
OK BTCUSDT BTC/USDT
filtered out: 1
FILTERED SOLUSDT SOL/USDT
not trading: 1
NOT_TRADING OLDUSDT status=BREAK
missing: 1
MISSING MADEUPUSDT
```

Use this before running:

```bash
uv run python examples/run_download.py --file configs/spot-1d.yaml --freq daily
```

## Put Symbols Into A Config

After choosing symbols, add them to your downloader config:

```yaml
asset: spot
data_type: klines
interval: 1d
symbols:
  - BTCUSDT
  - ETHUSDT
  - SOLUSDT
start_date: 2024-01-01
end_date: 2026-04-06
destination_dir: ./data
```

Then validate the config:

```bash
uv run python examples/check_tradable_symbols.py --file configs/spot-1d.yaml
```

## Important Distinction

This command checks the live Binance Spot exchange. It answers:

```text
Is this symbol currently tradable on Binance Spot?
```

With margin flags, it can also answer:

```text
Is this symbol currently listed as a cross/isolated margin pair?
Is the base or quote asset currently listed as borrowable?
```

It does not answer:

```text
Does Binance historical data exist for every date I want?
Will a borrow request for my exact account, size, region, and risk state succeed?
```

Historical files on `data.binance.vision` can include symbols that are no longer
tradable today. A symbol can also be currently tradable while still having a
shorter listing history than your requested `start_date`.

For that reason, a normal workflow is:

1. List or validate currently tradable symbols with
   `examples/check_tradable_symbols.py`.
2. Run the downloader.
3. Let the downloader report missing historical ZIP files, usually as `404`
   errors, when the requested date range predates a symbol listing or Binance
   does not publish that file.

## Troubleshooting

- Network failure: confirm that `https://api.binance.com` is reachable.
- Margin or borrowability command says an API key is required: set
  `BINANCE_API_KEY` or pass `--api-key`. A secret key is not needed for this
  command.
- Empty output with `--quote`: the quote asset may not have currently tradable
  spot pairs, or it may be misspelled.
- Config validation exits `1`: remove missing or non-trading symbols from the
  config, or relax the margin/borrowability flags if the filtered symbols are
  acceptable for your workflow.
- Historical download still gets `404`: tradability is current exchange status,
  not proof that every historical file exists.
- Borrow check passes but an order/borrow still fails: Binance can apply
  account-specific, region-specific, risk, balance, and size constraints that
  are not proven by the public asset list.

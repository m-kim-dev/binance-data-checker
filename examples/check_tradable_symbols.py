from __future__ import annotations

from argparse import ArgumentParser
import os
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.binance_symbols import (
    BinanceAPIError,
    check_symbols,
    fetch_cross_margin_pairs,
    fetch_exchange_info,
    fetch_isolated_margin_pairs,
    fetch_margin_assets,
    parse_margin_assets,
    parse_margin_pairs,
    parse_symbols,
    tradable_symbols,
)


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--file", help="YAML downloader config to validate")
    parser.add_argument("--quote", help="Only list symbols with this quote asset, e.g. USDT")
    parser.add_argument("--require-market-order", action="store_true")
    parser.add_argument(
        "--margin",
        choices=("none", "cross", "isolated", "any"),
        default="none",
        help="Filter to symbols available for cross margin, isolated margin, or either",
    )
    parser.add_argument(
        "--require-borrowable",
        nargs="?",
        const="base",
        choices=("base", "quote", "both", "any"),
        help=(
            "Require borrowable margin assets. Use base for shorting the base asset, "
            "quote for margin buying, both, or any. Defaults to base when no value is given."
        ),
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("BINANCE_API_KEY"),
        help=(
            "Binance API key for margin metadata endpoints. "
            "Defaults to BINANCE_API_KEY."
        ),
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit printed list output")
    args = parser.parse_args()

    if args.margin in {"isolated", "any"} and not args.api_key:
        parser.error("--margin isolated/any requires --api-key or BINANCE_API_KEY")
    if args.require_borrowable and not args.api_key:
        parser.error("--require-borrowable requires --api-key or BINANCE_API_KEY")

    cross_margin_symbols = set()
    isolated_margin_symbols = set()
    borrowable_assets = set()

    if args.margin in {"cross", "any"} and args.api_key:
        cross_margin_symbols = {
            item.symbol
            for item in parse_margin_pairs(fetch_cross_margin_pairs(api_key=args.api_key))
            if item.is_margin_trade
        }
    if args.margin in {"isolated", "any"}:
        isolated_margin_symbols = {
            item.symbol
            for item in parse_margin_pairs(fetch_isolated_margin_pairs(api_key=args.api_key))
            if item.is_margin_trade
        }
    if args.require_borrowable:
        borrowable_assets = {
            item.asset
            for item in parse_margin_assets(fetch_margin_assets(api_key=args.api_key))
            if item.is_borrowable
        }

    if args.file:
        with open(args.file) as f:
            config = yaml.safe_load(f)
        requested = config["symbols"]
        exchange_info = fetch_exchange_info(requested)
        tradable, missing, not_trading, filtered_out = check_symbols(
            requested,
            exchange_info,
            margin=args.margin,
            cross_margin_symbols=cross_margin_symbols,
            isolated_margin_symbols=isolated_margin_symbols,
            borrowable_assets=borrowable_assets,
            require_borrowable=args.require_borrowable,
        )
        print(f"tradable: {len(tradable)}")
        for item in tradable:
            print(f"OK {item.symbol} {item.base_asset}/{item.quote_asset}")
        if filtered_out:
            print(f"filtered out: {len(filtered_out)}")
            for item in filtered_out:
                print(f"FILTERED {item.symbol} {item.base_asset}/{item.quote_asset}")
        if not_trading:
            print(f"not trading: {len(not_trading)}")
            for item in not_trading:
                print(f"NOT_TRADING {item.symbol} status={item.status}")
        if missing:
            print(f"missing: {len(missing)}")
            for symbol in missing:
                print(f"MISSING {symbol}")
        if missing or not_trading or filtered_out:
            raise SystemExit(1)
        return

    symbols = tradable_symbols(
        parse_symbols(fetch_exchange_info()),
        quote_asset=args.quote,
        require_market_order=args.require_market_order,
        margin=args.margin,
        cross_margin_symbols=cross_margin_symbols,
        isolated_margin_symbols=isolated_margin_symbols,
        borrowable_assets=borrowable_assets,
        require_borrowable=args.require_borrowable,
    )
    if args.limit:
        symbols = symbols[: args.limit]
    for item in symbols:
        print(f"{item.symbol},{item.base_asset},{item.quote_asset},{item.status}")


if __name__ == "__main__":
    try:
        main()
    except BinanceAPIError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc

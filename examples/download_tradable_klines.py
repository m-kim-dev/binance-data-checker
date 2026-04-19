from __future__ import annotations

from argparse import ArgumentParser
import asyncio
import os
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.klines_orchestrator import download_all_tradable_klines
from src.paths import Config


async def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--file", required=True, help="YAML downloader config")
    parser.add_argument("--freq", choices=("daily", "monthly"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit-symbols", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("BINANCE_API_KEY"),
        help="Binance API key for margin metadata endpoints",
    )
    args = parser.parse_args()

    with open(args.file) as f:
        cfg = Config(**yaml.safe_load(f))

    summary = await download_all_tradable_klines(
        cfg,
        freq=args.freq,
        api_key=args.api_key,
        dry_run=args.dry_run,
        limit_symbols=args.limit_symbols,
        force=args.force,
        continue_on_error=args.continue_on_error,
    )
    print(f"run_id: {summary.run_id}")
    print(f"symbols: {len(summary.symbols)}")
    print(f"urls: {summary.url_count}")
    print(f"failed: {summary.failed}")
    print(f"manifest: {summary.manifest_path}")


if __name__ == "__main__":
    asyncio.run(main())

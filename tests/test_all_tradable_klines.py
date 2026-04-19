from __future__ import annotations

import asyncio
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from src.klines_orchestrator import download_all_tradable_klines
from src.paths import Config
from src.symbol_resolver import resolve_symbols


EXCHANGE_INFO = {
    "symbols": [
        {
            "symbol": "BTCUSDT",
            "status": "TRADING",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "orderTypes": ["LIMIT", "MARKET"],
            "permissions": ["SPOT"],
            "isMarginTradingAllowed": True,
        },
        {
            "symbol": "BNBUSDT",
            "status": "TRADING",
            "baseAsset": "BNB",
            "quoteAsset": "USDT",
            "orderTypes": ["LIMIT"],
            "permissions": ["SPOT"],
            "isMarginTradingAllowed": False,
        },
        {
            "symbol": "ETHBTC",
            "status": "TRADING",
            "baseAsset": "ETH",
            "quoteAsset": "BTC",
            "orderTypes": ["LIMIT", "MARKET"],
            "permissions": ["SPOT"],
            "isMarginTradingAllowed": False,
        },
    ]
}


class AllTradableKlinesTests(unittest.TestCase):
    def test_config_rejects_symbols_and_symbol_source_together(self) -> None:
        with self.assertRaises(ValueError):
            Config(
                asset="spot",
                data_type="klines",
                interval="1d",
                start_date="2026-03-01",
                end_date="2026-03-31",
                destination_dir="./data",
                symbols=["BTCUSDT"],
                symbol_source="tradable",
            )

    def test_config_normalizes_yaml_dates_to_strings(self) -> None:
        cfg = Config(
            asset="spot",
            data_type="klines",
            interval="1d",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
            destination_dir="./data",
            symbols=["btcusdt"],
        )

        self.assertEqual(cfg.start_date, "2026-03-01")
        self.assertEqual(cfg.end_date, "2026-03-31")
        self.assertEqual(cfg.symbols, ["BTCUSDT"])

    def test_resolve_tradable_symbols_applies_quote_and_market_filters(self) -> None:
        cfg = Config(
            asset="spot",
            data_type="klines",
            interval="1d",
            start_date="2026-03-01",
            end_date="2026-03-31",
            destination_dir="./data",
            symbol_source="tradable",
            quote_asset="usdt",
            require_market_order=True,
        )

        with mock.patch("src.symbol_resolver.fetch_exchange_info", return_value=EXCHANGE_INFO):
            result = resolve_symbols(cfg)

        self.assertEqual(result.source, "tradable")
        self.assertEqual(result.symbol_names, ["BTCUSDT"])
        self.assertEqual(result.total_exchange_symbols, 3)

    def test_orchestrator_dry_run_writes_manifest_without_downloading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cfg = Config(
                asset="spot",
                data_type="klines",
                interval="1d",
                start_date="2026-03-01",
                end_date="2026-03-31",
                destination_dir=str(tmp_path / "data"),
                db_path=str(tmp_path / "file.db"),
                symbols=["BTCUSDT"],
                batch_size=1,
                missing_frequency="monthly",
            )

            summary = asyncio.run(download_all_tradable_klines(cfg, dry_run=True))

            self.assertTrue(summary.dry_run)
            self.assertEqual(summary.symbols, ["BTCUSDT"])
            self.assertEqual(summary.url_count, 1)
            self.assertEqual(len(summary.batches), 1)
            self.assertEqual(summary.batches[0].status, "dry_run")
            self.assertTrue(summary.manifest_path.exists())

            manifest = json.loads(summary.manifest_path.read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["symbol_count"], 1)
            self.assertEqual(manifest["batches"][0]["url_count"], 1)


if __name__ == "__main__":
    unittest.main()

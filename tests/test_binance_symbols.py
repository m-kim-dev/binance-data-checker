from __future__ import annotations

import unittest

from src.binance_symbols import (
    check_symbols,
    parse_margin_assets,
    parse_margin_pairs,
    parse_symbols,
    tradable_symbols,
)


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
            "symbol": "ETHUSDT",
            "status": "BREAK",
            "baseAsset": "ETH",
            "quoteAsset": "USDT",
            "orderTypes": ["LIMIT", "MARKET"],
            "permissions": ["SPOT"],
            "isMarginTradingAllowed": False,
        },
        {
            "symbol": "BNBBTC",
            "status": "TRADING",
            "baseAsset": "BNB",
            "quoteAsset": "BTC",
            "orderTypes": ["LIMIT"],
            "permissions": ["SPOT"],
            "isMarginTradingAllowed": False,
        },
    ]
}


class BinanceSymbolsTests(unittest.TestCase):
    def test_parse_symbols_maps_exchange_info(self) -> None:
        symbols = parse_symbols(EXCHANGE_INFO)

        self.assertEqual(symbols[0].symbol, "BTCUSDT")
        self.assertEqual(symbols[0].status, "TRADING")
        self.assertEqual(symbols[0].base_asset, "BTC")
        self.assertEqual(symbols[0].quote_asset, "USDT")
        self.assertEqual(symbols[0].order_types, ("LIMIT", "MARKET"))
        self.assertTrue(symbols[0].is_margin_trading_allowed)

    def test_parse_margin_pairs_and_assets(self) -> None:
        pairs = parse_margin_pairs(
            [{"symbol": "BTCUSDT", "isMarginTrade": True}, {"symbol": "ETHUSDT"}]
        )
        assets = parse_margin_assets(
            [{"asset": "BTC", "isBorrowable": True}, {"asset": "ETH", "isBorrowable": False}]
        )

        self.assertEqual([item.symbol for item in pairs], ["BTCUSDT", "ETHUSDT"])
        self.assertTrue(pairs[0].is_margin_trade)
        self.assertTrue(pairs[1].is_margin_trade)
        self.assertEqual([item.asset for item in assets], ["BTC", "ETH"])
        self.assertTrue(assets[0].is_borrowable)
        self.assertFalse(assets[1].is_borrowable)

    def test_tradable_symbols_filters_status_quote_and_market_order(self) -> None:
        symbols = parse_symbols(EXCHANGE_INFO)

        result = tradable_symbols(symbols, quote_asset="USDT", require_market_order=True)

        self.assertEqual([item.symbol for item in result], ["BTCUSDT"])

    def test_tradable_symbols_filters_margin_and_borrowable_assets(self) -> None:
        symbols = parse_symbols(EXCHANGE_INFO)

        result = tradable_symbols(
            symbols,
            quote_asset="USDT",
            margin="any",
            isolated_margin_symbols={"ETHUSDT"},
            borrowable_assets={"BTC"},
            require_borrowable="base",
        )

        self.assertEqual([item.symbol for item in result], ["BTCUSDT"])

    def test_check_symbols_splits_tradable_missing_and_not_trading(self) -> None:
        tradable, missing, not_trading, filtered_out = check_symbols(
            ["btcusdt", "ethusdt", "missingusdt"], EXCHANGE_INFO
        )

        self.assertEqual([item.symbol for item in tradable], ["BTCUSDT"])
        self.assertEqual(missing, ["MISSINGUSDT"])
        self.assertEqual([item.symbol for item in not_trading], ["ETHUSDT"])
        self.assertEqual(filtered_out, [])

    def test_check_symbols_splits_filtered_out_symbols(self) -> None:
        tradable, missing, not_trading, filtered_out = check_symbols(
            ["btcusdt", "bnbbtc"],
            EXCHANGE_INFO,
            margin="cross",
            borrowable_assets={"BTC"},
            require_borrowable="quote",
        )

        self.assertEqual([item.symbol for item in tradable], [])
        self.assertEqual(missing, [])
        self.assertEqual(not_trading, [])
        self.assertEqual([item.symbol for item in filtered_out], ["BTCUSDT", "BNBBTC"])


if __name__ == "__main__":
    unittest.main()

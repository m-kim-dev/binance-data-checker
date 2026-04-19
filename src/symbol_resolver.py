from __future__ import annotations

from dataclasses import dataclass

from src.binance_symbols import (
    BinanceSymbol,
    fetch_cross_margin_pairs,
    fetch_exchange_info,
    fetch_isolated_margin_pairs,
    fetch_margin_assets,
    parse_margin_assets,
    parse_margin_pairs,
    parse_symbols,
    tradable_symbols,
)
from src.paths import Config


@dataclass(frozen=True)
class SymbolResolution:
    symbols: list[BinanceSymbol]
    source: str
    total_exchange_symbols: int | None
    filters: dict[str, str | bool | None]

    @property
    def symbol_names(self) -> list[str]:
        return [item.symbol for item in self.symbols]


def resolve_symbols(cfg: Config, api_key: str | None = None) -> SymbolResolution:
    filters: dict[str, str | bool | None] = {
        "quote_asset": cfg.quote_asset,
        "require_market_order": cfg.require_market_order,
        "margin": cfg.margin,
        "require_borrowable": cfg.require_borrowable,
    }

    if cfg.symbols:
        symbols = [
            BinanceSymbol(
                symbol=symbol.upper(),
                status="CONFIGURED",
                base_asset="",
                quote_asset="",
                order_types=(),
                permissions=(),
                is_margin_trading_allowed=False,
            )
            for symbol in cfg.symbols
        ]
        return SymbolResolution(
            symbols=symbols,
            source="config",
            total_exchange_symbols=None,
            filters=filters,
        )

    if cfg.symbol_source != "tradable":
        raise ValueError(f"Unsupported symbol_source: {cfg.symbol_source}")
    if cfg.margin in {"isolated", "any"} and not api_key:
        raise ValueError("margin isolated/any requires a Binance API key")
    if cfg.require_borrowable and not api_key:
        raise ValueError("require_borrowable requires a Binance API key")

    exchange_symbols = parse_symbols(fetch_exchange_info())
    cross_margin_symbols: set[str] = set()
    isolated_margin_symbols: set[str] = set()
    borrowable_assets: set[str] = set()

    if cfg.margin in {"cross", "any"} and api_key:
        cross_margin_symbols = {
            item.symbol
            for item in parse_margin_pairs(fetch_cross_margin_pairs(api_key=api_key))
            if item.is_margin_trade
        }
    if cfg.margin in {"isolated", "any"}:
        isolated_margin_symbols = {
            item.symbol
            for item in parse_margin_pairs(fetch_isolated_margin_pairs(api_key=api_key))
            if item.is_margin_trade
        }
    if cfg.require_borrowable:
        borrowable_assets = {
            item.asset
            for item in parse_margin_assets(fetch_margin_assets(api_key=api_key))
            if item.is_borrowable
        }

    symbols = tradable_symbols(
        exchange_symbols,
        quote_asset=cfg.quote_asset,
        require_market_order=cfg.require_market_order,
        margin=cfg.margin,
        cross_margin_symbols=cross_margin_symbols,
        isolated_margin_symbols=isolated_margin_symbols,
        borrowable_assets=borrowable_assets,
        require_borrowable=cfg.require_borrowable,
    )
    return SymbolResolution(
        symbols=symbols,
        source="tradable",
        total_exchange_symbols=len(exchange_symbols),
        filters=filters,
    )

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen


BINANCE_SPOT_API_BASE_URL = "https://api.binance.com"


class BinanceAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class BinanceSymbol:
    symbol: str
    status: str
    base_asset: str
    quote_asset: str
    order_types: tuple[str, ...]
    permissions: tuple[str, ...]
    is_margin_trading_allowed: bool


@dataclass(frozen=True)
class MarginPair:
    symbol: str
    is_margin_trade: bool


@dataclass(frozen=True)
class MarginAsset:
    asset: str
    is_borrowable: bool


def fetch_exchange_info(
    symbols: list[str] | None = None,
    base_url: str = BINANCE_SPOT_API_BASE_URL,
    timeout: float = 30,
) -> dict:
    params = ""
    if symbols:
        normalized = [symbol.upper() for symbol in symbols]
        params = "?" + urlencode({"symbols": json.dumps(normalized, separators=(",", ":"))})

    with urlopen(f"{base_url}/api/v3/exchangeInfo{params}", timeout=timeout) as response:
        return json.load(response)


def fetch_cross_margin_pairs(
    symbols: list[str] | None = None,
    base_url: str = BINANCE_SPOT_API_BASE_URL,
    timeout: float = 30,
    api_key: str | None = None,
) -> list[dict]:
    params = ""
    if symbols:
        normalized = [symbol.upper() for symbol in symbols]
        params = "?" + urlencode({"symbol": ",".join(normalized)})

    with open_json_url(
        f"{base_url}/sapi/v1/margin/allPairs{params}",
        timeout=timeout,
        api_key=api_key,
    ) as response:
        return json.load(response)


def fetch_isolated_margin_pairs(
    symbols: list[str] | None = None,
    base_url: str = BINANCE_SPOT_API_BASE_URL,
    timeout: float = 30,
    api_key: str | None = None,
) -> list[dict]:
    params = ""
    if symbols:
        normalized = [symbol.upper() for symbol in symbols]
        params = "?" + urlencode({"symbol": ",".join(normalized)})

    with open_json_url(
        f"{base_url}/sapi/v1/margin/isolated/allPairs{params}",
        timeout=timeout,
        api_key=api_key,
    ) as response:
        return json.load(response)


def fetch_margin_assets(
    base_url: str = BINANCE_SPOT_API_BASE_URL,
    timeout: float = 30,
    api_key: str | None = None,
) -> list[dict]:
    with open_json_url(
        f"{base_url}/sapi/v1/margin/allAssets",
        timeout=timeout,
        api_key=api_key,
    ) as response:
        return json.load(response)


def open_json_url(url: str, timeout: float, api_key: str | None = None):
    headers = {}
    if api_key:
        headers["X-MBX-APIKEY"] = api_key
    request = Request(url, headers=headers)

    try:
        return urlopen(request, timeout=timeout)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise BinanceAPIError(f"Binance API request failed: HTTP {exc.code} {body}") from exc


def parse_symbols(exchange_info: dict) -> list[BinanceSymbol]:
    parsed = []
    for item in exchange_info.get("symbols", []):
        parsed.append(
            BinanceSymbol(
                symbol=item["symbol"],
                status=item["status"],
                base_asset=item.get("baseAsset", ""),
                quote_asset=item.get("quoteAsset", ""),
                order_types=tuple(item.get("orderTypes", [])),
                permissions=tuple(item.get("permissions", [])),
                is_margin_trading_allowed=bool(
                    item.get("isMarginTradingAllowed", "MARGIN" in item.get("permissions", []))
                ),
            )
        )
    return parsed


def parse_margin_pairs(items: list[dict]) -> list[MarginPair]:
    parsed = []
    for item in items:
        symbol = item.get("symbol")
        if not symbol:
            continue
        parsed.append(
            MarginPair(
                symbol=symbol.upper(),
                is_margin_trade=bool(item.get("isMarginTrade", True)),
            )
        )
    return parsed


def parse_margin_assets(items: list[dict]) -> list[MarginAsset]:
    parsed = []
    for item in items:
        asset = item.get("asset")
        if not asset:
            continue
        parsed.append(
            MarginAsset(
                asset=asset.upper(),
                is_borrowable=bool(item.get("isBorrowable", False)),
            )
        )
    return parsed


def tradable_symbols(
    symbols: list[BinanceSymbol],
    quote_asset: str | None = None,
    require_market_order: bool = False,
    margin: str = "none",
    cross_margin_symbols: set[str] | None = None,
    isolated_margin_symbols: set[str] | None = None,
    borrowable_assets: set[str] | None = None,
    require_borrowable: str | None = None,
) -> list[BinanceSymbol]:
    quote = quote_asset.upper() if quote_asset else None
    cross = cross_margin_symbols or set()
    isolated = isolated_margin_symbols or set()
    borrowable = borrowable_assets or set()
    result = []
    for symbol in symbols:
        if symbol.status != "TRADING":
            continue
        if quote and symbol.quote_asset != quote:
            continue
        if require_market_order and "MARKET" not in symbol.order_types:
            continue
        if not matches_margin_filter(symbol, margin, cross, isolated):
            continue
        if require_borrowable and not matches_borrowable_filter(
            symbol, borrowable, require_borrowable
        ):
            continue
        result.append(symbol)
    return sorted(result, key=lambda item: item.symbol)


def matches_margin_filter(
    symbol: BinanceSymbol,
    margin: str,
    cross_margin_symbols: set[str],
    isolated_margin_symbols: set[str],
) -> bool:
    if margin == "none":
        return True

    is_cross = (
        symbol.is_margin_trading_allowed
        or "MARGIN" in symbol.permissions
        or symbol.symbol in cross_margin_symbols
    )
    is_isolated = symbol.symbol in isolated_margin_symbols

    if margin == "cross":
        return is_cross
    if margin == "isolated":
        return is_isolated
    if margin == "any":
        return is_cross or is_isolated
    raise ValueError(f"Unsupported margin filter: {margin}")


def matches_borrowable_filter(
    symbol: BinanceSymbol,
    borrowable_assets: set[str],
    require_borrowable: str,
) -> bool:
    base = symbol.base_asset.upper()
    quote = symbol.quote_asset.upper()

    if require_borrowable == "base":
        return base in borrowable_assets
    if require_borrowable == "quote":
        return quote in borrowable_assets
    if require_borrowable == "both":
        return base in borrowable_assets and quote in borrowable_assets
    if require_borrowable == "any":
        return base in borrowable_assets or quote in borrowable_assets
    raise ValueError(f"Unsupported borrowable filter: {require_borrowable}")


def check_symbols(
    requested_symbols: list[str],
    exchange_info: dict,
    margin: str = "none",
    cross_margin_symbols: set[str] | None = None,
    isolated_margin_symbols: set[str] | None = None,
    borrowable_assets: set[str] | None = None,
    require_borrowable: str | None = None,
) -> tuple[list[BinanceSymbol], list[str], list[BinanceSymbol], list[BinanceSymbol]]:
    requested = [symbol.upper() for symbol in requested_symbols]
    by_symbol = {item.symbol: item for item in parse_symbols(exchange_info)}
    tradable = []
    missing = []
    not_trading = []
    filtered_out = []

    for symbol in requested:
        item = by_symbol.get(symbol)
        if item is None:
            missing.append(symbol)
        elif item.status == "TRADING":
            if not matches_margin_filter(
                item,
                margin,
                cross_margin_symbols or set(),
                isolated_margin_symbols or set(),
            ):
                filtered_out.append(item)
            elif require_borrowable and not matches_borrowable_filter(
                item, borrowable_assets or set(), require_borrowable
            ):
                filtered_out.append(item)
            else:
                tradable.append(item)
        else:
            not_trading.append(item)

    return tradable, missing, not_trading, filtered_out

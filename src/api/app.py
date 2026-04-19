import os
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import duckdb
from fastapi import FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DB_TIME_OFFSET_SECONDS = 9 * 60 * 60
SUPPORTED_INTERVALS = {
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "3d",
    "1w",
    "1M",
}


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorPayload


class PageInfo(BaseModel):
    limit: int
    next_cursor: str | None = None


class Candle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_asset_volume: float | None = None
    number_of_trades: int | None = None
    taker_buy_base_volume: float | None = None
    taker_buy_quote_volume: float | None = None


class CandlePage(BaseModel):
    symbol: str
    interval: str
    timezone: Literal["UTC"] = "UTC"
    items: list[dict[str, Any]]
    page: PageInfo


class RatioCandle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    base_close: float
    quote_close: float


class RatioPage(BaseModel):
    base_symbol: str
    quote_symbol: str
    interval: str
    timezone: Literal["UTC"] = "UTC"
    items: list[RatioCandle]
    page: PageInfo


class SymbolSummary(BaseModel):
    symbol: str
    intervals: list[str]


class SymbolIntervalCoverage(BaseModel):
    interval: str
    first_time: int
    last_time: int
    count: int


class SymbolDetail(BaseModel):
    symbol: str
    base_asset: str
    quote_asset: str
    intervals: list[SymbolIntervalCoverage]


class LinePoint(BaseModel):
    time: int
    value: float


class Marker(BaseModel):
    time: int
    position: Literal["aboveBar", "belowBar", "inBar"]
    color: str
    shape: Literal["arrowUp", "arrowDown", "circle", "square"]
    text: str | None = None


class Strategy(BaseModel):
    id: str
    name: str
    description: str | None = None
    parameters: dict[str, Any]


class IndicatorPreviewRequest(BaseModel):
    symbol: str
    interval: str
    indicator: str
    params: dict[str, Any] = Field(default_factory=dict)
    from_: int | None = Field(default=None, alias="from")
    to: int | None = None


class CreateBacktestRequest(BaseModel):
    strategy_id: str
    symbol: str
    interval: str
    from_: int = Field(alias="from")
    to: int
    initial_capital: float = Field(gt=0)
    fee_bps: float = 0
    slippage_bps: float = 0
    parameters: dict[str, Any] = Field(default_factory=dict)


class BacktestMetrics(BaseModel):
    total_return_pct: float
    max_drawdown_pct: float
    sharpe: float
    win_rate_pct: float
    trade_count: int


class Backtest(BaseModel):
    id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    strategy_id: str
    symbol: str
    interval: str
    metrics: BacktestMetrics | None = None
    links: dict[str, str] = Field(default_factory=dict)


class CreateOrderRequest(BaseModel):
    account_id: str
    symbol: str
    side: Literal["buy", "sell"]
    type: Literal["market", "limit", "stop_limit"]
    quantity: float = Field(gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    time_in_force: Literal["GTC", "IOC", "FOK"] = "GTC"


class Order(BaseModel):
    id: str
    account_id: str
    symbol: str
    side: Literal["buy", "sell"]
    type: Literal["market", "limit", "stop_limit"]
    quantity: float
    status: Literal["new", "partially_filled", "filled", "cancelled", "rejected"]
    limit_price: float | None = None
    stop_price: float | None = None
    created_at: str


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("BINANCE_DB_PATH", "file.db")
    trading_mode: str = os.getenv("TRADING_MODE", "readonly")


settings = Settings()
app = FastAPI(
    title="Binance Algorithmic Trading UI API",
    version="0.1.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

STRATEGIES = [
    Strategy(
        id="ma_cross",
        name="Moving Average Cross",
        description="Fast and slow moving-average crossover.",
        parameters={"fast_length": 20, "slow_length": 50},
    ),
    Strategy(
        id="breakout",
        name="Range Breakout",
        description="Breakout above the recent high with volatility filter.",
        parameters={"lookback": 30, "atr_length": 14},
    ),
]
BACKTESTS: dict[str, Backtest] = {}
ORDERS: dict[str, Order] = {}


def api_error(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message, "details": details}},
    )


def connect() -> duckdb.DuckDBPyConnection:
    try:
        return duckdb.connect(settings.db_path, read_only=True)
    except duckdb.Error as exc:
        raise api_error(
            500,
            "database_unavailable",
            f"Unable to open DuckDB database: {settings.db_path}",
            {"error": str(exc)},
        ) from exc


def validate_symbol(symbol: str) -> str:
    value = symbol.upper()
    if not value.isalnum() or len(value) > 20:
        raise api_error(400, "invalid_symbol", f"Invalid symbol: {symbol}")
    return value


def validate_interval(interval: str) -> str:
    if interval not in SUPPORTED_INTERVALS:
        raise api_error(400, "invalid_interval", f"Invalid interval: {interval}")
    return interval


def split_symbol(symbol: str) -> tuple[str, str]:
    for quote in ("USDT", "USDC", "FDUSD", "BTC", "ETH", "BNB"):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)], quote
    return symbol, ""


def db_epoch_sql(column: str = "open_time") -> str:
    return f"cast(epoch({column}) as bigint) - {DB_TIME_OFFSET_SECONDS}"


def assert_symbol_interval(con: duckdb.DuckDBPyConnection, symbol: str, interval: str) -> None:
    exists = con.execute(
        """
        select 1
        from binance_candles
        where symbol = ? and interval = ?
        limit 1
        """,
        [symbol, interval],
    ).fetchone()
    if exists is None:
        raise api_error(
            404,
            "series_not_found",
            f"No candles found for {symbol} {interval}",
            {"symbol": symbol, "interval": interval},
        )


def candle_from_row(row: tuple[Any, ...]) -> Candle:
    return Candle(
        time=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
        quote_asset_volume=float(row[6]),
        number_of_trades=int(row[7]),
        taker_buy_base_volume=float(row[8]),
        taker_buy_quote_volume=float(row[9]),
    )


def fetch_candles(
    symbol: str,
    interval: str,
    from_time: int | None,
    to_time: int | None,
    limit: int,
    order: Literal["asc", "desc"],
) -> list[Candle]:
    con = connect()
    try:
        assert_symbol_interval(con, symbol, interval)
        clauses = ["symbol = ?", "interval = ?"]
        params: list[Any] = [symbol, interval]
        epoch_expr = db_epoch_sql()
        if from_time is not None:
            clauses.append(f"{epoch_expr} >= ?")
            params.append(from_time)
        if to_time is not None:
            clauses.append(f"{epoch_expr} < ?")
            params.append(to_time)

        rows = con.execute(
            f"""
            select
              {epoch_expr} as time,
              open,
              high,
              low,
              close,
              volume,
              quote_asset_volume,
              number_of_trades,
              taker_buy_base_volume,
              taker_buy_quote_volume
            from binance_candles
            where {" and ".join(clauses)}
            order by open_time {order}
            limit ?
            """,
            [*params, limit],
        ).fetchall()
        return [candle_from_row(row) for row in rows]
    finally:
        con.close()


def filter_fields(candles: list[Candle], fields: str | None) -> list[dict[str, Any]]:
    allowed = set(Candle.model_fields)
    selected = [field.strip() for field in fields.split(",")] if fields else []
    if not selected:
        return [candle.model_dump(exclude_none=True) for candle in candles]
    invalid = [field for field in selected if field not in allowed]
    if invalid:
        raise api_error(
            400,
            "invalid_fields",
            "Unknown candle fields requested",
            {"fields": invalid},
        )
    return [
        {key: value for key, value in candle.model_dump(exclude_none=True).items() if key in selected}
        for candle in candles
    ]


def fetch_ratio_candles(
    base_symbol: str,
    quote_symbol: str,
    interval: str,
    from_time: int | None,
    to_time: int | None,
    limit: int,
    order: Literal["asc", "desc"],
) -> list[RatioCandle]:
    con = connect()
    try:
        assert_symbol_interval(con, base_symbol, interval)
        assert_symbol_interval(con, quote_symbol, interval)
        epoch_expr = db_epoch_sql("base.open_time")
        clauses = [
            "base.symbol = ?",
            "quote.symbol = ?",
            "base.interval = ?",
            "quote.interval = ?",
            "base.open_time = quote.open_time",
            "quote.open != 0",
            "quote.close != 0",
        ]
        params: list[Any] = [base_symbol, quote_symbol, interval, interval]
        if from_time is not None:
            clauses.append(f"{epoch_expr} >= ?")
            params.append(from_time)
        if to_time is not None:
            clauses.append(f"{epoch_expr} < ?")
            params.append(to_time)

        rows = con.execute(
            f"""
            select
              {epoch_expr} as time,
              base.open / quote.open as open,
              greatest(base.open / quote.open, base.close / quote.close) as high,
              least(base.open / quote.open, base.close / quote.close) as low,
              base.close / quote.close as close,
              base.close as base_close,
              quote.close as quote_close
            from binance_candles base
            join binance_candles quote
              on base.open_time = quote.open_time
             and base.interval = quote.interval
            where {" and ".join(clauses)}
            order by base.open_time {order}
            limit ?
            """,
            [*params, limit],
        ).fetchall()
        return [
            RatioCandle(
                time=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                base_close=float(row[5]),
                quote_close=float(row[6]),
            )
            for row in rows
        ]
    finally:
        con.close()


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Any, exc: HTTPException) -> Response:
    from fastapi.responses import JSONResponse

    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
    )


@app.get("/api/v1/health")
def get_health() -> dict[str, Any]:
    try:
        con = connect()
        con.execute("select 1").fetchone()
        con.close()
        connected = True
    except HTTPException:
        connected = False
    return {
        "status": "ok" if connected else "degraded",
        "database": {
            "path": settings.db_path,
            "connected": connected,
            "readonly": True,
        },
    }


@app.get("/api/v1/markets")
def list_markets() -> dict[str, Any]:
    return {"items": [{"id": "binance_spot", "exchange": "binance", "market_type": "spot"}]}


@app.get("/api/v1/symbols")
def list_symbols() -> dict[str, list[SymbolSummary]]:
    con = connect()
    try:
        rows = con.execute(
            """
            select symbol, list(distinct interval order by interval) as intervals
            from binance_candles
            group by symbol
            order by symbol
            """
        ).fetchall()
        return {"items": [SymbolSummary(symbol=row[0], intervals=list(row[1])) for row in rows]}
    finally:
        con.close()


@app.get("/api/v1/intervals")
def list_intervals(symbol: str = Query(...)) -> dict[str, Any]:
    symbol = validate_symbol(symbol)
    con = connect()
    try:
        rows = con.execute(
            """
            select distinct interval
            from binance_candles
            where symbol = ?
            order by interval
            """,
            [symbol],
        ).fetchall()
        if not rows:
            raise api_error(404, "symbol_not_found", f"Unknown symbol: {symbol}")
        return {"symbol": symbol, "items": [row[0] for row in rows]}
    finally:
        con.close()


@app.get("/api/v1/symbols/{symbol}")
def get_symbol(symbol: str) -> SymbolDetail:
    symbol = validate_symbol(symbol)
    con = connect()
    try:
        rows = con.execute(
            f"""
            select
              interval,
              min({db_epoch_sql()}) as first_time,
              max({db_epoch_sql()}) as last_time,
              count(*) as count
            from binance_candles
            where symbol = ?
            group by interval
            order by interval
            """,
            [symbol],
        ).fetchall()
        if not rows:
            raise api_error(404, "symbol_not_found", f"Unknown symbol: {symbol}")
        base, quote = split_symbol(symbol)
        return SymbolDetail(
            symbol=symbol,
            base_asset=base,
            quote_asset=quote,
            intervals=[
                SymbolIntervalCoverage(
                    interval=row[0],
                    first_time=int(row[1]),
                    last_time=int(row[2]),
                    count=int(row[3]),
                )
                for row in rows
            ],
        )
    finally:
        con.close()


@app.get("/api/v1/candles")
def get_candles(
    symbol: str = Query(...),
    interval: str = Query(...),
    from_: int | None = Query(default=None, ge=0, alias="from"),
    to: int | None = Query(default=None, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
    cursor: str | None = Query(default=None),
    order: Literal["asc", "desc"] = "asc",
    fields: str | None = None,
) -> CandlePage:
    if cursor:
        raise api_error(400, "cursor_not_supported", "Cursor pagination is not implemented yet")
    if from_ is not None and to is not None and from_ >= to:
        raise api_error(400, "invalid_range", "`from` must be lower than `to`")
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
    candles = fetch_candles(symbol, interval, from_, to, limit, order)
    return CandlePage(
        symbol=symbol,
        interval=interval,
        items=filter_fields(candles, fields),
        page=PageInfo(limit=limit, next_cursor=None),
    )


@app.get("/api/v1/candles/latest")
def get_latest_candle(symbol: str = Query(...), interval: str = Query(...)) -> dict[str, Any]:
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
    candles = fetch_candles(symbol, interval, None, None, 1, "desc")
    if not candles:
        raise api_error(404, "series_not_found", f"No candles found for {symbol} {interval}")
    return {"symbol": symbol, "interval": interval, "item": candles[0].model_dump(exclude_none=True)}


@app.get("/api/v1/ratios")
def get_ratio(
    base_symbol: str = Query(...),
    quote_symbol: str = Query(...),
    interval: str = Query(...),
    from_: int | None = Query(default=None, ge=0, alias="from"),
    to: int | None = Query(default=None, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
    order: Literal["asc", "desc"] = "asc",
) -> RatioPage:
    if from_ is not None and to is not None and from_ >= to:
        raise api_error(400, "invalid_range", "`from` must be lower than `to`")
    base_symbol = validate_symbol(base_symbol)
    quote_symbol = validate_symbol(quote_symbol)
    if base_symbol == quote_symbol:
        raise api_error(
            400,
            "invalid_ratio",
            "Ratio symbols must be different",
            {"base_symbol": base_symbol, "quote_symbol": quote_symbol},
        )
    interval = validate_interval(interval)
    candles = fetch_ratio_candles(base_symbol, quote_symbol, interval, from_, to, limit, order)
    return RatioPage(
        base_symbol=base_symbol,
        quote_symbol=quote_symbol,
        interval=interval,
        items=candles,
        page=PageInfo(limit=limit, next_cursor=None),
    )


@app.get("/api/v1/symbols/{symbol}/intervals/{interval}/indicators")
def list_indicator_series(symbol: str, interval: str) -> dict[str, Any]:
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
    con = connect()
    try:
        assert_symbol_interval(con, symbol, interval)
    finally:
        con.close()
    return {
        "items": [
            {"id": "sma_20", "name": "SMA 20", "kind": "line", "style": {"color": "#f59e0b"}},
            {"id": "sma_50", "name": "SMA 50", "kind": "line", "style": {"color": "#38bdf8"}},
        ]
    }


@app.post("/api/v1/indicators/preview")
def preview_indicator(request: IndicatorPreviewRequest) -> dict[str, list[LinePoint]]:
    symbol = validate_symbol(request.symbol)
    interval = validate_interval(request.interval)
    indicator = request.indicator.lower()
    if indicator not in {"sma", "moving_average"}:
        raise api_error(400, "unsupported_indicator", f"Unsupported indicator: {request.indicator}")
    length = int(request.params.get("length", 20))
    if length < 1 or length > 500:
        raise api_error(400, "invalid_indicator_length", "Indicator length must be between 1 and 500")

    candles = fetch_candles(symbol, interval, request.from_, request.to, 5000, "asc")
    points: list[LinePoint] = []
    closes: list[float] = []
    for candle in candles:
        closes.append(candle.close)
        if len(closes) >= length:
            window = closes[-length:]
            points.append(LinePoint(time=candle.time, value=sum(window) / length))
    return {"items": points}


@app.get("/api/v1/strategies")
def list_strategies() -> dict[str, list[Strategy]]:
    return {"items": STRATEGIES}


@app.get("/api/v1/strategies/{strategy_id}/signals")
def get_strategy_signals(
    strategy_id: str,
    symbol: str = Query(...),
    interval: str = Query(...),
    from_: int | None = Query(default=None, ge=0, alias="from"),
    to: int | None = Query(default=None, ge=0),
) -> dict[str, list[Marker]]:
    if strategy_id not in {strategy.id for strategy in STRATEGIES}:
        raise api_error(404, "strategy_not_found", f"Unknown strategy: {strategy_id}")
    symbol = validate_symbol(symbol)
    interval = validate_interval(interval)
    candles = fetch_candles(symbol, interval, from_, to, 5000, "asc")
    if len(candles) < 2:
        return {"items": []}
    buy_index = max(0, len(candles) // 3)
    sell_index = max(buy_index + 1, (len(candles) * 2) // 3)
    sell_index = min(sell_index, len(candles) - 1)
    return {
        "items": [
            Marker(
                time=candles[buy_index].time,
                position="belowBar",
                color="#0f8b8d",
                shape="arrowUp",
                text="Long",
            ),
            Marker(
                time=candles[sell_index].time,
                position="aboveBar",
                color="#c2410c",
                shape="arrowDown",
                text="Exit",
            ),
        ]
    }


@app.post("/api/v1/backtests", status_code=202)
def create_backtest(request: CreateBacktestRequest) -> Backtest:
    candles = fetch_candles(
        validate_symbol(request.symbol),
        validate_interval(request.interval),
        request.from_,
        request.to,
        5000,
        "asc",
    )
    if len(candles) < 2:
        raise api_error(400, "not_enough_data", "Backtest range needs at least two candles")
    start = candles[0].close
    end = candles[-1].close
    total_return = ((end - start) / start) * 100
    backtest_id = uuid.uuid4().hex
    backtest = Backtest(
        id=backtest_id,
        status="succeeded",
        strategy_id=request.strategy_id,
        symbol=request.symbol,
        interval=request.interval,
        metrics=BacktestMetrics(
            total_return_pct=total_return,
            max_drawdown_pct=0.0,
            sharpe=0.0,
            win_rate_pct=100.0 if total_return >= 0 else 0.0,
            trade_count=1,
        ),
        links={
            "equity": f"/api/v1/backtests/{backtest_id}/equity",
            "trades": f"/api/v1/backtests/{backtest_id}/trades",
        },
    )
    BACKTESTS[backtest_id] = backtest
    return backtest


@app.get("/api/v1/backtests/{backtest_id}")
def get_backtest(backtest_id: str) -> Backtest:
    backtest = BACKTESTS.get(backtest_id)
    if backtest is None:
        raise api_error(404, "backtest_not_found", f"Unknown backtest: {backtest_id}")
    return backtest


@app.get("/api/v1/backtests/{backtest_id}/equity")
def get_backtest_equity(backtest_id: str) -> dict[str, list[LinePoint]]:
    backtest = BACKTESTS.get(backtest_id)
    if backtest is None:
        raise api_error(404, "backtest_not_found", f"Unknown backtest: {backtest_id}")
    candles = fetch_candles(backtest.symbol, backtest.interval, None, None, 120, "desc")
    ordered = list(reversed(candles))
    equity = 10_000.0
    points = []
    previous = ordered[0].close if ordered else 0
    for candle in ordered:
        if previous:
            equity *= 1 + ((candle.close - previous) / previous)
        points.append(LinePoint(time=candle.time, value=equity))
        previous = candle.close
    return {"items": points}


@app.get("/api/v1/backtests/{backtest_id}/trades")
def get_backtest_trades(backtest_id: str) -> dict[str, Any]:
    backtest = BACKTESTS.get(backtest_id)
    if backtest is None:
        raise api_error(404, "backtest_not_found", f"Unknown backtest: {backtest_id}")
    return {"items": []}


@app.get("/api/v1/accounts")
def list_accounts() -> dict[str, Any]:
    return {"items": [{"id": "paper-main", "mode": "paper", "base_currency": "USDT", "equity": 10000.0}]}


@app.get("/api/v1/accounts/{account_id}/positions")
def list_positions(account_id: str) -> dict[str, Any]:
    if account_id != "paper-main":
        raise api_error(404, "account_not_found", f"Unknown account: {account_id}")
    return {"items": []}


@app.get("/api/v1/orders")
def list_orders(account_id: str | None = None, symbol: str | None = None) -> dict[str, Any]:
    items = list(ORDERS.values())
    if account_id:
        items = [order for order in items if order.account_id == account_id]
    if symbol:
        value = validate_symbol(symbol)
        items = [order for order in items if order.symbol == value]
    return {"items": items}


@app.post("/api/v1/orders", status_code=201)
def create_order(
    request: CreateOrderRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> Order:
    if settings.trading_mode == "readonly":
        raise api_error(403, "trading_disabled", "Trading endpoints are disabled in readonly mode")
    if len(idempotency_key) < 8:
        raise api_error(400, "invalid_idempotency_key", "Idempotency-Key must be at least 8 chars")
    order = Order(
        id=uuid.uuid4().hex,
        account_id=request.account_id,
        symbol=validate_symbol(request.symbol),
        side=request.side,
        type=request.type,
        quantity=request.quantity,
        status="new",
        limit_price=request.limit_price,
        stop_price=request.stop_price,
        created_at="2026-04-18T00:00:00Z",
    )
    ORDERS[order.id] = order
    return order


@app.delete("/api/v1/orders/{order_id}")
def cancel_order(order_id: str) -> Order:
    order = ORDERS.get(order_id)
    if order is None:
        raise api_error(404, "order_not_found", f"Unknown order: {order_id}")
    if order.status not in {"new", "partially_filled"}:
        raise api_error(409, "order_not_cancelable", f"Order cannot be cancelled: {order_id}")
    cancelled = order.model_copy(update={"status": "cancelled"})
    ORDERS[order_id] = cancelled
    return cancelled

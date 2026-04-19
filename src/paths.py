from dataclasses import dataclass
from pathlib import Path

@dataclass
class Config:
    asset: str
    data_type: str
    interval: str
    start_date: str
    end_date: str
    destination_dir: str
    symbols: list[str] | None = None
    symbol_source: str | None = None
    quote_asset: str | None = None
    require_market_order: bool = False
    margin: str = "none"
    require_borrowable: str | None = None
    db_path: str = "file.db"
    batch_size: int = 25
    download_concurrency: int = 10
    missing_frequency: str | None = None

    def __post_init__(self) -> None:
        if self.symbols and self.symbol_source:
            raise ValueError("Use either symbols or symbol_source, not both")
        if not self.symbols and not self.symbol_source:
            raise ValueError("Config requires symbols or symbol_source")
        if self.symbol_source and self.symbol_source != "tradable":
            raise ValueError(f"Unsupported symbol_source: {self.symbol_source}")
        if self.asset != "spot":
            raise ValueError(f"Unsupported asset: {self.asset}")
        if self.data_type != "klines":
            raise ValueError(f"Unsupported data_type: {self.data_type}")
        if self.margin not in {"none", "cross", "isolated", "any"}:
            raise ValueError(f"Unsupported margin filter: {self.margin}")
        if self.require_borrowable not in {None, "base", "quote", "both", "any"}:
            raise ValueError(f"Unsupported borrowable filter: {self.require_borrowable}")
        if self.missing_frequency not in {None, "daily", "monthly"}:
            raise ValueError(f"Unsupported missing_frequency: {self.missing_frequency}")
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if self.download_concurrency < 1:
            raise ValueError("download_concurrency must be at least 1")
        if self.symbols is not None:
            self.symbols = [symbol.upper() for symbol in self.symbols]
        if self.quote_asset is not None:
            self.quote_asset = self.quote_asset.upper()
        self.start_date = str(self.start_date)
        self.end_date = str(self.end_date)

def data_path(cfg: Config, symbol, freq):
    des = Path(cfg.destination_dir)
    return des / cfg.asset / freq / cfg.data_type / symbol / cfg.interval
    # return des / cfg.asset / freq / cfg.data_type / symbol / cfg.interval / f"{symbol}-{cfg.interval}.parquet"

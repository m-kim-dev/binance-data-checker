from dataclasses import dataclass
from pathlib import Path

@dataclass
class Config:
    asset: str
    data_type: str
    interval: str
    symbols: list[str]
    start_date: str
    end_date: str
    destination_dir: str

def data_path(cfg: Config, symbol, freq):
    des = Path(cfg.destination_dir)
    return des / cfg.asset / freq / cfg.data_type / symbol / cfg.interval
    # return des / cfg.asset / freq / cfg.data_type / symbol / cfg.interval / f"{symbol}-{cfg.interval}.parquet"

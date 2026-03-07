# assuming you have downloaded some data
from datetime import datetime
from collections import namedtuple
from src.checker import check_missing
from src.formatter import convert_format
from src.column_namer import add_column_names
from src.pipeline import Pipeline

opt = {
  "base_path": "./data/spot/monthly/klines/",
  "interval": "1d"
}

Pair = namedtuple('Pair', ['pair', 'start_date', 'end_date'])

checklist = [
  Pair("BTCUSDT", datetime(2017, 8, 1), datetime(2026, 2, 1)),
  Pair("ETHUSDT", datetime(2017, 9, 1), datetime(2026, 2, 1)),
]

pipeline = Pipeline([
  # ("download", download, {}),
  ("check", check_missing, {}),
  ("format", convert_format, {'format': 'parquet'}),
  ("add column names", add_column_names, {'columns': ('open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_vol', 'trades', 'taker_base', 'taker_quote', 'ignore')}),
  # ("fix-timestamp", fix_timestamp, {"columns": ('open_time', 'close_time'), "unit": 's'})
], opt)

for item in checklist:
  pipeline.run(item)

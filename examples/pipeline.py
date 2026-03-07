# assuming you have downloaded some data
from datetime import datetime
from src.checker import check_missing
from src.formatter import convert_format
from src.pipeline import Pipeline
from collections import namedtuple

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
  # ("header", add_header, {'header': ('open_time', 'open', 'high', 'low', 'close', 'volume')}),
  # ("fix-timestamp", fix_timestamp, {"columns": ('open_time', 'close_time'), "unit": 's'})
], opt)

for item in checklist:
  pipeline.run(item);

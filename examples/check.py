# assuming you have downloaded some data
from datetime import datetime
from src.checker import check_missing

base_path = "./data/spot/monthly/klines/"
interval = "1d"

checklist = [
  ("BTCUSDT", datetime(2017, 8, 1), datetime(2026, 2, 1)),
  ("ETHUSDT", datetime(2017, 9, 1), datetime(2026, 2, 1)),
]

for pair, start_date, end_date in checklist:
  check_missing(pair, interval, start_date, end_date, base_path)

import os
from datetime import datetime

def check_missing(pair, interval, start_date, end_date, base_path):
  folder = os.path.join(base_path, pair, interval)
  date = start_date
  missing = []

  while date <= end_date:
    # print(date)
    filename = f"{pair}-{interval}-{date.year}-{date.month:02d}.csv"
    if not os.path.isfile(os.path.join(folder, filename)):
      missing.append(filename)
    # increment month
    if date.month == 12:
      date = datetime(date.year + 1, 1, 1)
    else:
      date = datetime(date.year, date.month + 1, 1)

  if missing:
    print(f"{pair}-{interval}: Missing files:")
    for f in missing:
      print(f)
  else:
    print(f"{pair}-{interval}: {start_date} ~ {end_date}: All files present!")



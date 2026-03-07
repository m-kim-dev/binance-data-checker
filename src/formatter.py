from pathlib import Path
import duckdb

def _convert_format(pair, interval, format, datapath, **kwargs):
  if format == 'parquet':
    csv_pattern = Path(datapath) / "*.csv"
    parquet_path = Path(datapath) / f"{pair}-{interval}.parquet"
    print("Converted")
    print("from: ", csv_pattern)
    duckdb.sql(f"COPY(SELECT * FROM read_csv_auto('{csv_pattern}')) to '{parquet_path}'(FORMAT parquet);")
    print("to:", parquet_path)
    return
  raise ValueError("no such format: ", format)

def convert_format(opts):
  _convert_format(**opts)
  return opts



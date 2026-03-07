from pathlib import Path
import duckdb

def _add_column_names(pair, interval, format, datapath, columns, **kwargs):
  def column_string(columns):
    lst = []
    n_digits = len(str(len(columns) - 1))
    for i in range(len(columns)):
      col_num = str(i).zfill(n_digits)
      lst.append(f"column{col_num} AS {columns[i]}")
    return ", ".join(lst)

  if format == 'parquet':
    parquet_path = Path(datapath) / f"{pair}-{interval}.parquet"
    query = f"""
      COPY (
        SELECT {column_string(columns)}
        FROM '{parquet_path}'
      )
      TO '{parquet_path}'
      (FORMAT PARQUET);
      """
    duckdb.sql(query)
    return
  raise ValueError("no such format: ", format)

def add_column_names(opts):
  _add_column_names(**opts)
  return opts



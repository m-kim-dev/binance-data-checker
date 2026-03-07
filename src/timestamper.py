import duckdb

def _set_timestamp_in_second(datafile, format, columns_to_fix, columns, **kwargs):
  def select_string(columns_to_fix, columns):
    return ", ".join([
      f"""
      CASE
          WHEN CAST({column} AS BIGINT) > 1e15
              THEN CAST({column} / 1000000 AS BIGINT)  
          WHEN CAST({column} AS BIGINT) > 1e12
              THEN CAST({column} / 1000 AS BIGINT)
          ELSE CAST(open_time AS BIGINT)
      END AS {column}
      """ if column in columns_to_fix else column for column in columns 
    ])

  query = f"""
    COPY (
        SELECT
          {select_string(columns_to_fix, columns)}
        FROM '{datafile}'
    )
    TO '{datafile}'
    (FORMAT {format});
  """
  # print(query)
  duckdb.sql(query)
  return

def set_timestamp_in_second(opt):
  _set_timestamp_in_second(**opt)

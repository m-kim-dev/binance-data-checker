from zipfile import ZipFile

from src.paths import data_path, Config

NORMALIZE_SECOND_MACRO_SQL = """-- sql
create or replace macro time_in_second(t) as
to_timestamp(
    case
        when t >= 1e15 then t / 1e6
        when t >= 1e12 then t / 1e3
    end
);
"""

LOAD_CSV_TO_DB_SQL = """-- sql
insert or ignore into binance_candles
select 
    $1,
    $2,
  time_in_second(open_time) as open_time,
  time_in_second(close_time) as close_time,
  open, high, low, close, volume,
  quote_asset_volume,
  number_of_trades,
  taker_buy_base_volume,
  taker_buy_quote_volume
  from read_csv($3, columns={
    'open_time': 'BIGINT',
    'open': 'DOUBLE',
    'high': 'DOUBLE',
    'low': 'DOUBLE',
    'close': 'DOUBLE',
    'volume': 'DOUBLE',
    'close_time': 'BIGINT',
    'quote_asset_volume': 'DOUBLE',
    'number_of_trades': 'BIGINT',
    'taker_buy_base_volume': 'DOUBLE',
    'taker_buy_quote_volume': 'DOUBLE',
    'ignore': 'DOUBLE'
  }) as temp;
"""


CREATE_TABLE_SQL = """-- sql
create table if not exists binance_candles (
    symbol VARCHAR not null,
    interval VARCHAR not null,
    open_time TIMESTAMP not null,
    close_time TIMESTAMP not null,

    open DOUBLE not null,
    high DOUBLE not null,
    low DOUBLE not null,
    close DOUBLE not null,

    volume DOUBLE not null,
    quote_asset_volume DOUBLE not null,

    number_of_trades BIGINT not null,
    taker_buy_base_volume DOUBLE not null,
    taker_buy_quote_volume DOUBLE not null,

    primary key (symbol, interval, open_time)
);
"""


def insert_from_zip(con, cfg, freq):
    for symbol in cfg.symbols:
        dpath = data_path(cfg, symbol, freq)
        for zip_path in dpath.glob("*.zip"):
            with ZipFile(zip_path, "r") as zf:
                zf.extractall(dpath)
        con.execute(NORMALIZE_SECOND_MACRO_SQL)
        con.execute(CREATE_TABLE_SQL).fetchall()
        params = [symbol, cfg.interval, str(dpath / "*.csv")]
        con.execute(LOAD_CSV_TO_DB_SQL, params).fetchall()


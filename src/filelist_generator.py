from src.data_inserter import ensure_candle_table

MISSING_DAYS_MACRO_SQL = """ -- sql
create or replace temp macro missing_days(sym, iv, start_d, end_d) as table ( 
with actual as (
    select distinct cast(open_time as date) as d from binance_candles where symbol = sym and interval = iv
), expected as (
    select generate_series as d
    from
    generate_series(
    cast(start_d as date),
    cast(end_d as date),
    interval 1 day
    )
) select d from expected e anti join actual a on a.d = e.d);
"""

MISSING_DAYS_SQL = """ -- sql
select date_trunc('day', d) as day from missing_days($1, $2, $3, $4);
"""

MISSING_MONTHS_SQL = """ -- sql
with mcnt as (
    select date_trunc('month', d) as month, count(*) as cnt from missing_days($1, $2, $3, $4) group by 1
) select month, cnt, extract(day from last_day(month)) as full_cnt from mcnt where cnt = full_cnt;
"""

def build_datelist(con, cfg, freq):
    if freq not in {"daily", "monthly"}:
        raise ValueError(f"no such option: {freq}")
    if not cfg.symbols:
        raise ValueError("build_datelist requires cfg.symbols")

    dl_files = {}
    dl_files[freq] = {}
    # dl_files = {"monthly": {}, "daily": {}}
    ensure_candle_table(con)
    con.execute(MISSING_DAYS_MACRO_SQL)
    for symbol in cfg.symbols:
        dl_files[freq][symbol] = {}
        if freq == "monthly":
            res = con.execute(MISSING_MONTHS_SQL, [symbol, cfg.interval, cfg.start_date, cfg.end_date]).fetchall()
        elif freq == "daily":
            res = con.execute(MISSING_DAYS_SQL, [symbol, cfg.interval, cfg.start_date, cfg.end_date]).fetchall()
        dl_files[freq][symbol][cfg.interval] = res
    return dl_files



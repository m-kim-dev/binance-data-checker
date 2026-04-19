BINANCE_DATA_DOWNLOAD_BASE_URL = "https://data.binance.vision" 

def build_urls_aux(freq, symbol, interval, file_format, dates):
    if freq not in {"daily", "monthly"}:
        raise ValueError(f"Unsupported frequency: {freq}")
    date_format = "%Y-%m" if freq == "monthly" else "%Y-%m-%d"
    return [
        (
            f"{BINANCE_DATA_DOWNLOAD_BASE_URL}/data/spot/{freq}/klines/"
            f"{symbol}/{interval}/{symbol}-{interval}-{d[0].strftime(date_format)}.{file_format}"
        )
        for d in dates
    ]

def build_urls(date_lists):
    urls = []
    for freq in date_lists:
        if freq not in {"daily", "monthly"}:
            raise ValueError(f"Unsupported frequency: {freq}")
        for sym in date_lists[freq]:
            for itv in date_lists[freq][sym]:
                urls += build_urls_aux(freq, sym, itv, "zip", date_lists[freq][sym][itv])
    return urls

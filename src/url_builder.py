BINANCE_DATA_DOWNLOAD_BASE_URL = "https://data.binance.vision" 

def build_urls_aux(freq, symbol, interval, format, dates):
    return [f"{BINANCE_DATA_DOWNLOAD_BASE_URL}/data/spot/{freq}/klines/{symbol}/{interval}/{symbol}-{interval}-{d[0].strftime("%Y-%m" if freq == "monthly" else "%Y-%m-%d")}.{format}" for d in dates]

def build_urls(dict):
    urls = []
    for freq in dict:
        for sym in dict[freq]:
            for itv in dict[freq][sym]:
                urls += build_urls_aux(freq, sym, itv, "zip", dict[freq][sym][itv])
    return urls

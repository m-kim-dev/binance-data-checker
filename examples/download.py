# dependency: binance-bulk-downloader
from binance_bulk_downloader.downloader import BinanceBulkDownloader

symbols = ['BTCUSDT', 'ETHUSDT']

downloader = BinanceBulkDownloader(
  data_type="klines",
  data_frequency="1d",
  asset="spot",
  timeperiod_per_file="monthly",
  symbols = symbols
)
downloader.run_download()


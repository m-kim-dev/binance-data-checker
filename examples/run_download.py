from argparse import ArgumentParser
import asyncio
from pathlib import Path
import sys

import duckdb
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.paths import Config
from src.filelist_generator import build_datelist
from src.downloader import concurrent_download
from src.url_builder import build_urls
from src.data_inserter import insert_from_zip


async def main():
    parser = ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--freq", choices=("daily", "monthly"))
    args = parser.parse_args()
    with open(args.file) as f:
        data = yaml.safe_load(f)
        cfg = Config(**data)
        freq = args.freq or cfg.missing_frequency or "daily"
        with duckdb.connect(cfg.db_path) as con: 
            dates = build_datelist(con, cfg, freq)
            urls = build_urls(dates)
            await concurrent_download(
                urls,
                cfg.download_concurrency,
                destination_dir=cfg.destination_dir,
                skip_existing=True,
            )
            insert_from_zip(con, cfg, freq)

if __name__ == "__main__":
    asyncio.run(main())

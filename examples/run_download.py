from argparse import ArgumentParser
import asyncio

import duckdb
import yaml

from src.paths import data_path, Config
from src.filelist_generator import build_datelist
from src.downloader import concurrent_download
from src.url_builder import build_urls
from src.data_inserter import insert_from_zip


async def main():
    parser = ArgumentParser()
    parser.add_argument("--file")
    parser.add_argument("--freq")
    args = parser.parse_args()
    with open(args.file) as f:
        data = yaml.safe_load(f)
        cfg = Config(**data)
        with duckdb.connect("file.db") as con: 
            dates = build_datelist(con, cfg, args.freq)
            urls = build_urls(dates)
            await concurrent_download(urls, 10)
            insert_from_zip(con, cfg, args.freq)

if __name__ == "__main__":
    asyncio.run(main())

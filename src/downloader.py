import asyncio
from asyncio import Semaphore
import aiohttp
from urllib.parse import urlparse
from pathlib import Path

async def download(client, url, semaphore):
    async with semaphore:
        async with client.get(url) as resp:
            if resp.status == 200:
                path = Path(urlparse(url).path.lstrip("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('wb') as f:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        f.write(chunk)
            # else do nothing

async def concurrent_download(urls, n):
    semaphore = Semaphore(n)
    async with aiohttp.ClientSession() as client:
        requests = [download(client, url, semaphore) for url in urls]
        await asyncio.gather(*requests)

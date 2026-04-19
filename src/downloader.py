import asyncio
from asyncio import Semaphore
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import aiohttp


CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class DownloadResult:
    url: str
    path: Path
    status: int | None
    ok: bool
    error: str | None = None
    result: str = "downloaded"


class DownloadError(RuntimeError):
    def __init__(self, failures: list[DownloadResult]) -> None:
        self.failures = failures
        summary = ", ".join(f"{item.url} ({item.status or item.error})" for item in failures[:5])
        extra = "" if len(failures) <= 5 else f", and {len(failures) - 5} more"
        super().__init__(f"{len(failures)} download(s) failed: {summary}{extra}")


def destination_path(url: str, destination_dir: str | Path = ".") -> Path:
    parsed = urlparse(url)
    parts = Path(parsed.path.lstrip("/")).parts
    if parts and parts[0] == "data":
        parts = parts[1:]
    if not parts:
        raise ValueError(f"URL has no file path: {url}")
    return Path(destination_dir).joinpath(*parts)


async def download(
    client,
    url: str,
    semaphore: Semaphore,
    destination_dir: str | Path = ".",
    retries: int = 2,
    skip_existing: bool = False,
    expected_missing_statuses: set[int] | None = None,
) -> DownloadResult:
    path = destination_path(url, destination_dir)
    if skip_existing and path.exists():
        return DownloadResult(url, path, None, True, result="skipped")

    expected_missing_statuses = expected_missing_statuses or set()
    last_status: int | None = None
    last_error: str | None = None

    for attempt in range(retries + 1):
        try:
            async with semaphore:
                async with client.get(url) as resp:
                    last_status = resp.status
                    if resp.status != 200:
                        last_error = f"HTTP {resp.status}"
                        if resp.status in expected_missing_statuses:
                            return DownloadResult(
                                url,
                                path,
                                resp.status,
                                True,
                                last_error,
                                "missing_remote",
                            )
                        if attempt < retries:
                            await asyncio.sleep(0.25 * (2**attempt))
                            continue
                        return DownloadResult(
                            url, path, resp.status, False, last_error, "failed"
                        )

                    path.parent.mkdir(parents=True, exist_ok=True)
                    tmp_path = path.with_suffix(path.suffix + ".part")
                    with tmp_path.open("wb") as f:
                        async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                            f.write(chunk)
                    tmp_path.replace(path)
                    return DownloadResult(url, path, resp.status, True, result="downloaded")
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            last_error = str(exc)
            if attempt < retries:
                await asyncio.sleep(0.25 * (2**attempt))
                continue
            return DownloadResult(url, path, last_status, False, last_error, "failed")

    return DownloadResult(url, path, last_status, False, last_error, "failed")


async def concurrent_download(
    urls,
    n: int,
    destination_dir: str | Path = ".",
    retries: int = 2,
    skip_existing: bool = False,
    expected_missing_statuses: set[int] | None = None,
    raise_on_failure: bool = True,
) -> list[DownloadResult]:
    if n < 1:
        raise ValueError("concurrency must be at least 1")

    semaphore = Semaphore(n)
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=120)
    async with aiohttp.ClientSession(timeout=timeout) as client:
        requests = [
            download(
                client,
                url,
                semaphore,
                destination_dir,
                retries,
                skip_existing,
                expected_missing_statuses,
            )
            for url in urls
        ]
        results = await asyncio.gather(*requests)

    failures = [result for result in results if not result.ok]
    if failures and raise_on_failure:
        raise DownloadError(failures)
    return results

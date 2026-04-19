from __future__ import annotations

import asyncio
import os
from pathlib import Path
import unittest
from unittest import mock
from zipfile import ZipFile

from src import downloader
from src.data_inserter import safe_extract_zip


class FakeContent:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.requested_sizes: list[int] = []

    async def iter_chunked(self, chunk_size: int):
        self.requested_sizes.append(chunk_size)
        for chunk in self._chunks:
            yield chunk


class FakeResponse:
    def __init__(self, status: int = 200, chunks: list[bytes] | None = None) -> None:
        self.status = status
        self.content = FakeContent(chunks or [])

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = responses
        self.requested_urls: list[str] = []

    def get(self, url: str) -> FakeResponse:
        self.requested_urls.append(url)
        index = min(len(self.requested_urls) - 1, len(self._responses) - 1)
        return self._responses[index]


class FakeClientSession:
    instances: list["FakeClientSession"] = []
    response_by_url: dict[str, FakeResponse] = {}

    def __init__(self, *args, **kwargs) -> None:
        self.entered = False
        self.exited = False
        self.requested_urls: list[str] = []
        FakeClientSession.instances.append(self)

    async def __aenter__(self) -> "FakeClientSession":
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.exited = True
        return None

    def get(self, url: str) -> FakeResponse:
        self.requested_urls.append(url)
        return self.response_by_url[url]


class DownloaderTests(unittest.TestCase):
    def test_destination_path_uses_configured_destination_dir(self) -> None:
        url = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/file.zip"

        path = downloader.destination_path(url, "/tmp/custom-data")

        self.assertEqual(
            path,
            Path("/tmp/custom-data/spot/monthly/klines/BTCUSDT/1m/file.zip"),
        )

    def test_download_streams_response_to_destination_dir(self) -> None:
        response = FakeResponse(chunks=[b"abc", b"def"])
        client = FakeClient([response])
        url = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/file.zip"

        with tempfile_chdir(self) as tmp_path:
            result = asyncio.run(
                downloader.download(client, url, asyncio.Semaphore(1), "downloads")
            )
            output_path = (
                tmp_path / "downloads/spot/monthly/klines/BTCUSDT/1m/file.zip"
            )
            self.assertTrue(result.ok)
            self.assertEqual(result.path, Path("downloads/spot/monthly/klines/BTCUSDT/1m/file.zip"))
            self.assertEqual(output_path.read_bytes(), b"abcdef")
            self.assertFalse(output_path.with_suffix(".zip.part").exists())

        self.assertEqual(client.requested_urls, [url])
        self.assertEqual(response.content.requested_sizes, [64 * 1024])

    def test_download_returns_failure_after_non_200_response(self) -> None:
        client = FakeClient([FakeResponse(status=404)])

        with tempfile_chdir(self):
            result = asyncio.run(
                downloader.download(
                    client,
                    "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/missing.zip",
                    asyncio.Semaphore(1),
                    retries=0,
                )
            )

        self.assertFalse(result.ok)
        self.assertEqual(result.status, 404)
        self.assertEqual(result.error, "HTTP 404")

    def test_download_skips_existing_file(self) -> None:
        client = FakeClient([FakeResponse(chunks=[b"new"])])
        url = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/file.zip"

        with tempfile_chdir(self) as tmp_path:
            output_path = tmp_path / "downloads/spot/monthly/klines/BTCUSDT/1m/file.zip"
            output_path.parent.mkdir(parents=True)
            output_path.write_bytes(b"old")
            result = asyncio.run(
                downloader.download(
                    client,
                    url,
                    asyncio.Semaphore(1),
                    "downloads",
                    skip_existing=True,
                )
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.result, "skipped")
            self.assertEqual(output_path.read_bytes(), b"old")

        self.assertEqual(client.requested_urls, [])

    def test_download_categorizes_expected_404(self) -> None:
        client = FakeClient([FakeResponse(status=404)])

        with tempfile_chdir(self):
            result = asyncio.run(
                downloader.download(
                    client,
                    "https://data.binance.vision/data/spot/monthly/klines/NEWUSDT/1d/missing.zip",
                    asyncio.Semaphore(1),
                    retries=0,
                    expected_missing_statuses={404},
                )
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.status, 404)
        self.assertEqual(result.result, "missing_remote")

    def test_concurrent_download_raises_aggregate_failure(self) -> None:
        urls = [
            "https://example.test/a.zip",
            "https://example.test/b.zip",
        ]
        FakeClientSession.instances.clear()
        FakeClientSession.response_by_url = {
            urls[0]: FakeResponse(status=200, chunks=[b"a"]),
            urls[1]: FakeResponse(status=500),
        }

        with tempfile_chdir(self):
            with mock.patch.object(downloader.aiohttp, "ClientSession", FakeClientSession):
                with self.assertRaises(downloader.DownloadError) as ctx:
                    asyncio.run(downloader.concurrent_download(urls, 2, retries=0))

        self.assertEqual(len(FakeClientSession.instances), 1)
        self.assertTrue(FakeClientSession.instances[0].entered)
        self.assertTrue(FakeClientSession.instances[0].exited)
        self.assertEqual([failure.url for failure in ctx.exception.failures], [urls[1]])

    def test_safe_extract_zip_rejects_path_traversal(self) -> None:
        with tempfile_chdir(self) as tmp_path:
            zip_path = tmp_path / "unsafe.zip"
            with ZipFile(zip_path, "w") as zf:
                zf.writestr("../outside.csv", "bad")

            with self.assertRaises(ValueError):
                safe_extract_zip(zip_path, tmp_path / "out")

    def test_safe_extract_zip_extracts_safe_members(self) -> None:
        with tempfile_chdir(self) as tmp_path:
            zip_path = tmp_path / "safe.zip"
            with ZipFile(zip_path, "w") as zf:
                zf.writestr("inside.csv", "ok")

            safe_extract_zip(zip_path, tmp_path / "out")

            self.assertEqual((tmp_path / "out/inside.csv").read_text(), "ok")


class tempfile_chdir:
    def __init__(self, case: unittest.TestCase) -> None:
        self.case = case
        self.tmpdir = None
        self.previous_cwd = None

    def __enter__(self) -> Path:
        import tempfile

        self.tmpdir = tempfile.TemporaryDirectory()
        self.case.addCleanup(self.tmpdir.cleanup)
        self.previous_cwd = Path.cwd()
        os.chdir(self.tmpdir.name)
        return Path(self.tmpdir.name)

    def __exit__(self, exc_type, exc, tb) -> None:
        assert self.previous_cwd is not None
        os.chdir(self.previous_cwd)
        return None

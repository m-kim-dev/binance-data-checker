from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path

import duckdb

from src.data_inserter import InsertSummary, insert_from_zip
from src.downloader import DownloadError, DownloadResult, concurrent_download
from src.filelist_generator import build_datelist
from src.paths import Config
from src.symbol_resolver import SymbolResolution, resolve_symbols
from src.url_builder import build_urls


@dataclass(frozen=True)
class BatchSummary:
    index: int
    symbols: list[str]
    url_count: int
    downloaded: int = 0
    skipped: int = 0
    missing_remote: int = 0
    failed: int = 0
    inserted_zip_files: int = 0
    inserted_csv_files: int = 0
    status: str = "complete"


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    symbols: list[str]
    batches: list[BatchSummary]
    dry_run: bool
    manifest_path: Path

    @property
    def url_count(self) -> int:
        return sum(batch.url_count for batch in self.batches)

    @property
    def failed(self) -> int:
        return sum(batch.failed for batch in self.batches)


def utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_run_id(cfg: Config) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{cfg.asset}-{cfg.data_type}-{cfg.interval}"


def batch_items(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def batch_config(cfg: Config, symbols: list[str]) -> Config:
    return Config(
        asset=cfg.asset,
        data_type=cfg.data_type,
        interval=cfg.interval,
        start_date=cfg.start_date,
        end_date=cfg.end_date,
        destination_dir=cfg.destination_dir,
        symbols=symbols,
        quote_asset=cfg.quote_asset,
        require_market_order=cfg.require_market_order,
        margin=cfg.margin,
        require_borrowable=cfg.require_borrowable,
        db_path=cfg.db_path,
        batch_size=cfg.batch_size,
        download_concurrency=cfg.download_concurrency,
        missing_frequency=cfg.missing_frequency,
    )


def result_counts(results: list[DownloadResult]) -> dict[str, int]:
    counts = {"downloaded": 0, "skipped": 0, "missing_remote": 0, "failed": 0}
    for item in results:
        if item.result in counts:
            counts[item.result] += 1
        elif item.ok:
            counts["downloaded"] += 1
        else:
            counts["failed"] += 1
    return counts


def manifest_config(cfg: Config, freq: str) -> dict[str, object]:
    return {
        "asset": cfg.asset,
        "data_type": cfg.data_type,
        "interval": cfg.interval,
        "start_date": cfg.start_date,
        "end_date": cfg.end_date,
        "destination_dir": cfg.destination_dir,
        "db_path": cfg.db_path,
        "frequency": freq,
        "symbol_source": cfg.symbol_source,
        "quote_asset": cfg.quote_asset,
        "require_market_order": cfg.require_market_order,
        "margin": cfg.margin,
        "require_borrowable": cfg.require_borrowable,
        "batch_size": cfg.batch_size,
        "download_concurrency": cfg.download_concurrency,
    }


def write_manifest(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".part")
    tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp_path.replace(path)


async def download_all_tradable_klines(
    cfg: Config,
    freq: str | None = None,
    api_key: str | None = None,
    dry_run: bool = False,
    limit_symbols: int | None = None,
    force: bool = False,
    continue_on_error: bool = False,
) -> RunSummary:
    selected_freq = freq or cfg.missing_frequency or "daily"
    if selected_freq not in {"daily", "monthly"}:
        raise ValueError(f"Unsupported frequency: {selected_freq}")

    resolution = resolve_symbols(cfg, api_key=api_key)
    symbols = resolution.symbol_names
    if limit_symbols is not None:
        symbols = symbols[:limit_symbols]

    run_id = make_run_id(cfg)
    manifest_path = Path(cfg.destination_dir) / "manifests" / f"{run_id}.json"
    manifest = {
        "run_id": run_id,
        "started_at": utc_timestamp(),
        "finished_at": None,
        "dry_run": dry_run,
        "config": manifest_config(cfg, selected_freq),
        "symbol_resolution": symbol_resolution_manifest(resolution),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "batches": [],
        "status": "running",
    }
    write_manifest(manifest_path, manifest)

    summaries: list[BatchSummary] = []
    try:
        with duckdb.connect(cfg.db_path) as con:
            for index, symbols_batch in enumerate(batch_items(symbols, cfg.batch_size)):
                current_cfg = batch_config(cfg, symbols_batch)
                dates = build_datelist(con, current_cfg, selected_freq)
                urls = build_urls(dates)
                insert_summary = InsertSummary()
                if dry_run:
                    counts = {"downloaded": 0, "skipped": 0, "missing_remote": 0, "failed": 0}
                    status = "dry_run"
                else:
                    results = await concurrent_download(
                        urls,
                        cfg.download_concurrency,
                        destination_dir=cfg.destination_dir,
                        skip_existing=not force,
                        expected_missing_statuses={404},
                        raise_on_failure=False,
                    )
                    counts = result_counts(results)
                    failures = [item for item in results if not item.ok]
                    if failures and not continue_on_error:
                        status = "failed"
                    else:
                        insert_summary = insert_from_zip(con, current_cfg, selected_freq)
                        status = "complete" if not failures else "complete_with_errors"

                summary = BatchSummary(
                    index=index,
                    symbols=symbols_batch,
                    url_count=len(urls),
                    downloaded=counts["downloaded"],
                    skipped=counts["skipped"],
                    missing_remote=counts["missing_remote"],
                    failed=counts["failed"],
                    inserted_zip_files=insert_summary.zip_files,
                    inserted_csv_files=insert_summary.csv_files,
                    status=status,
                )
                summaries.append(summary)
                manifest["batches"] = [asdict(item) for item in summaries]
                write_manifest(manifest_path, manifest)

                if status == "failed":
                    manifest["status"] = "failed"
                    manifest["finished_at"] = utc_timestamp()
                    write_manifest(manifest_path, manifest)
                    failed_results = [item for item in results if not item.ok]
                    raise DownloadError(failed_results)
    except Exception:
        manifest["status"] = "failed"
        manifest["finished_at"] = utc_timestamp()
        manifest["batches"] = [asdict(item) for item in summaries]
        write_manifest(manifest_path, manifest)
        raise

    manifest["status"] = "complete"
    manifest["finished_at"] = utc_timestamp()
    manifest["batches"] = [asdict(item) for item in summaries]
    write_manifest(manifest_path, manifest)
    return RunSummary(
        run_id=run_id,
        symbols=symbols,
        batches=summaries,
        dry_run=dry_run,
        manifest_path=manifest_path,
    )


def symbol_resolution_manifest(resolution: SymbolResolution) -> dict[str, object]:
    return {
        "source": resolution.source,
        "total_exchange_symbols": resolution.total_exchange_symbols,
        "filters": resolution.filters,
    }


def run_download_all_tradable_klines(*args, **kwargs) -> RunSummary:
    return asyncio.run(download_all_tradable_klines(*args, **kwargs))

"""Seed pipeline CLI: build, restore, and inspect the portable demo seed.

The seed is a compressed snapshot of the catalog — songs, fingerprints, and
the source audio — used to demo the project offline (see ``demo.md``). The
pipeline is: link ingestion -> fingerprint processing -> dump -> compress.

    seed.py build    --links FILE [--out PATH]    # full pipeline
    seed.py ingest   --links FILE                 # download + insert pending songs
    seed.py process                               # fingerprint all pending songs (one-shot)
    seed.py dump     [--out PATH]                 # export songs+fingerprints+audio -> tar.gz
    seed.py restore  --file PATH                  # load a seed into the DB + restore audio

The links file has one Internet Archive link or identifier per line; blank
lines and lines starting with ``#`` are ignored. Accepted forms::

    https://archive.org/details/<id>
    https://archive.org/metadata/<id>
    https://archive.org/download/<id>/<file>
    <id>

Each subcommand is a thin async wrapper around ``core/`` so the logic is
reusable as Airflow tasks later.
"""
import argparse
import asyncio
from pathlib import Path
from typing import Optional

from config import UPLOAD_DIR
from core.catalog_service import ingest_links
from core.database import async_session
from core.logging import get_logger, setup_logging
from core.seed_service import dump_seed, load_seed
from core.song_service import process_pending_songs

logger = get_logger("seed")


def read_links(path: str) -> list[str]:
    """Read a links file: one IA link/identifier per line, # comments allowed."""
    lines = Path(path).read_text().splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


async def run_ingest(links: str) -> None:
    items = read_links(links)
    logger.info("seed ingest starting", links_file=links, count=len(items))
    async with async_session() as db:
        ingested = await ingest_links(db, items)
    logger.info("seed ingest complete", ingested=ingested)


async def run_process() -> None:
    async with async_session() as db:
        completed, failed = await process_pending_songs(db)
    logger.info("seed process complete", completed=completed, failed=failed)


async def run_dump(out: Optional[str], seed_dir: Optional[str] = None) -> Path:
    kwargs = {}
    if seed_dir:
        kwargs["seed_dir"] = seed_dir
    async with async_session() as db:
        return await dump_seed(db, out_path=out, **kwargs)


async def run_restore(seed_file: str) -> None:
    async with async_session() as db:
        summary = await load_seed(db, seed_file)
    logger.info("seed restore complete", **summary)


async def run_build(links: str, out: Optional[str]) -> None:
    await run_ingest(links)
    await run_process()
    path = await run_dump(out)
    logger.info("seed build complete", seed=str(path))


def main() -> None:
    setup_logging("seed")
    parser = argparse.ArgumentParser(
        description="Shanano seed pipeline (link ingestion -> processing -> dump -> compress)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser(
        "ingest", help="download + insert pending songs from a links file"
    )
    p_ingest.add_argument("--links", required=True, help="file with one IA link/identifier per line")
    p_ingest.add_argument("--upload-dir", default=UPLOAD_DIR, help="where downloaded audio is stored")

    sub.add_parser(
        "process", help="fingerprint every pending song (one-shot, no long-lived worker)"
    )

    p_dump = sub.add_parser("dump", help="export songs+fingerprints+audio to a compressed seed")
    p_dump.add_argument(
        "--out", default=None, help="output .tar.gz path (default: data/seed/shanano_seed_<ts>.tar.gz)"
    )
    p_dump.add_argument("--seed-dir", default=None, help="output dir for the default seed name")

    p_restore = sub.add_parser(
        "restore", help="load a seed into the DB and restore its audio files"
    )
    p_restore.add_argument("--file", required=True, help="path to the seed .tar.gz")
    p_restore.add_argument("--upload-dir", default=UPLOAD_DIR, help="where audio files are restored")

    p_build = sub.add_parser("build", help="full pipeline: ingest + process + dump")
    p_build.add_argument("--links", required=True, help="file with one IA link/identifier per line")
    p_build.add_argument("--out", default=None, help="output .tar.gz path (default: data/seed/shanano_seed_<ts>.tar.gz)")
    p_build.add_argument("--upload-dir", default=UPLOAD_DIR, help="where downloaded audio is stored")

    args = parser.parse_args()

    if args.command == "ingest":
        asyncio.run(run_ingest(args.links))
    elif args.command == "process":
        asyncio.run(run_process())
    elif args.command == "dump":
        asyncio.run(run_dump(args.out, args.seed_dir))
    elif args.command == "restore":
        asyncio.run(run_restore(args.file))
    elif args.command == "build":
        asyncio.run(run_build(args.links, args.out))


if __name__ == "__main__":
    main()

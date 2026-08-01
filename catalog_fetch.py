"""CLI entrypoint for one Internet Archive catalog fetch batch.

Structured so the core logic (``catalog_service.fetch_catalog_batch``) can be
reused later as an Airflow task: this module is only a thin async wrapper plus
argument parsing for the plain-K8s CronJob version of the same step.
"""
import argparse
import asyncio
from typing import Optional

from config import CATALOG_COLLECTION, CATALOG_MAX_ITEMS
from core.catalog_service import fetch_catalog_batch
from core.database import async_session
from core.logging import get_logger, setup_logging

logger = get_logger("catalog_fetch")


async def run_batch(
    collection: Optional[str] = None, max_items: Optional[int] = None
) -> int:
    """Run one fetch batch against the configured IA collection."""
    async with async_session() as db:
        return await fetch_catalog_batch(
            db,
            collection=collection or CATALOG_COLLECTION,
            max_items=max_items or CATALOG_MAX_ITEMS,
        )


def main() -> None:
    setup_logging("catalog_fetch")
    parser = argparse.ArgumentParser(
        description="Fetch one batch of songs from the Internet Archive catalog "
        "and insert them as pending songs."
    )
    parser.add_argument(
        "--collection",
        default=None,
        help=f"IA collection to query (default: $CATALOG_COLLECTION or {CATALOG_COLLECTION!r})",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help=f"Max items to fetch (default: $CATALOG_MAX_ITEMS or {CATALOG_MAX_ITEMS})",
    )
    args = parser.parse_args()

    ingested = asyncio.run(run_batch(args.collection, args.max_items))
    logger.info("catalog batch complete", ingested=ingested)


if __name__ == "__main__":
    main()

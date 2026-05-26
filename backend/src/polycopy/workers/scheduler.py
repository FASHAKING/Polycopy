import asyncio
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from polycopy.core.config import get_settings
from polycopy.core.db import init_db
from polycopy.core.logging import configure_logging, get_logger

log = get_logger(__name__)


async def _watcher_tick() -> None:
    from polycopy.workers.watcher import watch_once

    await watch_once()


async def _scout_tick() -> None:
    from polycopy.workers.scout import scout_once

    await scout_once()


async def _reconcile_tick() -> None:
    from polycopy.workers.reconcile import reconcile_once

    await reconcile_once()


async def run_async() -> None:
    configure_logging()
    settings = get_settings()
    await init_db()

    scheduler = AsyncIOScheduler(job_defaults={"coalesce": True, "max_instances": 1})
    scheduler.add_job(_watcher_tick, "interval", seconds=settings.watcher_poll_interval)
    scheduler.add_job(_scout_tick, "interval", seconds=settings.scout_poll_interval)
    scheduler.add_job(_reconcile_tick, "interval", seconds=settings.reconcile_poll_interval)
    scheduler.start()

    log.info(
        "worker.startup",
        watcher_interval=settings.watcher_poll_interval,
        scout_interval=settings.scout_poll_interval,
        reconcile_interval=settings.reconcile_poll_interval,
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    try:
        await stop.wait()
    finally:
        scheduler.shutdown(wait=False)
        log.info("worker.shutdown")


def run() -> None:
    asyncio.run(run_async())

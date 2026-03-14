"""CopyPoly — Main Application Entry Point.

Initializes logging, verifies DB connectivity, and starts
the scheduler with all data collection jobs.
"""

from __future__ import annotations

import asyncio
import signal
import sys

from copypoly.config import settings
from copypoly.logging import get_logger, setup_logging

log = get_logger(__name__)

# Shutdown flag
_shutdown_event = asyncio.Event()


async def verify_db_connection() -> bool:
    """Check that the database is reachable."""
    from copypoly.db.session import engine

    try:
        async with engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        log.info("database_connected", url=settings.database_url.split("@")[-1])
        return True
    except Exception as e:
        log.error("database_connection_failed", error=str(e))
        return False


async def run() -> None:
    """Main async execution loop."""
    setup_logging(settings.log_level.value)

    log.info(
        "starting_copypoly",
        version="0.1.0",
        trading_mode=settings.trading_mode.value,
        log_level=settings.log_level.value,
    )

    # Verify database connectivity
    if not await verify_db_connection():
        log.error("cannot_start", reason="Database connection failed")
        sys.exit(1)

    log.info(
        "configuration_loaded",
        leaderboard_interval=f"{settings.leaderboard_update_interval_minutes}m",
        position_interval=f"{settings.position_check_interval_seconds}s",
        market_interval=f"{settings.market_sync_interval_minutes}m",
    )

    # Initialize and start the data collection scheduler (unless disabled)
    import os
    if os.getenv("DISABLE_SCHEDULER", "").lower() not in ("1", "true", "yes"):
        from copypoly.collectors.scheduler import create_scheduler

        scheduler = create_scheduler()
        scheduler.start()
    else:
        log.info("scheduler_disabled", reason="DISABLE_SCHEDULER env var set")

    # Start the dashboard server (runs in background)
    import uvicorn
    from copypoly.dashboard.app import dashboard_app

    config = uvicorn.Config(
        dashboard_app,
        host="0.0.0.0",
        port=8000,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    log.info("copypoly_ready", mode=settings.trading_mode.value, dashboard="http://0.0.0.0:8000")

    # Run dashboard server (this blocks until shutdown)
    await server.serve()

    # Cleanup
    log.info("shutting_down")
    scheduler.shutdown(wait=False)

    from copypoly.db.session import dispose_engine

    await dispose_engine()
    log.info("copypoly_shutdown_complete")


def _handle_shutdown(sig: signal.Signals) -> None:
    """Handle OS shutdown signals gracefully."""
    log.info("shutdown_signal_received", signal=sig.name)
    _shutdown_event.set()


def main() -> None:
    """Entry point for the application."""
    loop = asyncio.new_event_loop()

    # Register shutdown handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_shutdown, sig)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            signal.signal(sig, lambda s, f: _handle_shutdown(signal.Signals(s)))

    try:
        loop.run_until_complete(run())
    except KeyboardInterrupt:
        log.info("keyboard_interrupt")
    finally:
        loop.close()


if __name__ == "__main__":
    main()

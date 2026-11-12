import asyncio
import logging

from datetime import datetime, timezone

from sqlalchemy import select, update

from app.core.config import settings
from app.database.database import AsyncSessionLocal
from app.database.models import Monitor
from app.services.monitor import (
    normalize_utc,
    trigger_alert,
)


logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Watchdog:

    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self.running = False

    async def check_expired_monitors(self):
        """
        Find expired ACTIVE monitors and transition them to DOWN.
        """

        now = utc_now()

        async with AsyncSessionLocal() as db:

            # Find potentially expired monitors.

            result = await db.execute(
                select(Monitor.id).where(
                    Monitor.status == "ACTIVE",
                    Monitor.expires_at <= now,
                )
            )

            expired_ids = result.scalars().all()

            if not expired_ids:
                return

            logger.info(
                "Watchdog found %d potentially expired monitors.",
                len(expired_ids),
            )

            # Attempt an atomic state transition

            for monitor_id in expired_ids:

                transition = await db.execute(
                    update(Monitor)
                    .where(
                        Monitor.id == monitor_id,
                        Monitor.status == "ACTIVE",
                        Monitor.expires_at <= now,
                        Monitor.alerted_at.is_(None),
                    )
                    .values(
                        status="DOWN",
                        alerted_at=now,
                    )
                    .execution_options(
                        synchronize_session=False
                    )
                )

                if transition.rowcount == 0:
                    # Another operation already handled it.
                    continue

                # Retrieve the updated monitor.

                await db.commit()

                monitor = await db.get(Monitor, monitor_id)

                if monitor is None:
                    continue

                # Trigger the alert.

                trigger_alert(monitor)

                logger.info(
                    "Monitor %s successfully transitioned to DOWN.",
                    monitor_id,
                )

    async def run(self):
        """
        Continuously execute the watchdog loop.
        """

        self.running = True

        logger.info(
            "Watchdog started. Polling interval: %s seconds.",
            self.interval,
        )

        try:

            while self.running:

                try:
                    await self.check_expired_monitors()

                except asyncio.CancelledError:
                    raise

                except Exception:
                    logger.exception(
                        "An error occurred during watchdog execution."
                    )

                await asyncio.sleep(self.interval)

        finally:
            self.running = False

            logger.info("Watchdog stopped.")

    def stop(self):
        self.running = False


watchdog = Watchdog(
    interval=settings.WATCHDOG_INTERVAL
)
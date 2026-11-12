import json
import logging

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Monitor
from app.schemas.monitor import MonitorCreate


logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_utc(value: datetime) -> datetime:
    """
    SQLite may return timezone-naive datetimes.

    Interpret naive values as UTC.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def trigger_alert(monitor: Monitor) -> None:
    """
    Simulate an alert by logging a JSON object.
    """

    alert = {
        "ALERT": f"Device {monitor.id} is down!",
        "time": utc_now().isoformat(),
    }

    logger.critical(json.dumps(alert))


class MonitorNotFoundError(Exception):
    pass


class MonitorAlreadyExistsError(Exception):
    pass


class MonitorExpiredError(Exception):
    pass


class MonitorStateError(Exception):
    pass


class MonitorService:

    @staticmethod
    async def register(
        db: AsyncSession,
        data: MonitorCreate,
    ) -> Monitor:

        existing = await db.get(Monitor, data.id)

        if existing:
            raise MonitorAlreadyExistsError(
                f"Monitor {data.id} already exists."
            )

        now = utc_now()

        monitor = Monitor(
            id=data.id,
            timeout=data.timeout,
            alert_email=str(data.alert_email),
            status="ACTIVE",
            created_at=now,
            last_heartbeat_at=now,
            expires_at=now + timedelta(seconds=data.timeout),
        )

        db.add(monitor)

        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise MonitorAlreadyExistsError(
                f"Monitor {data.id} already exists."
            )

        await db.refresh(monitor)

        return monitor

    @staticmethod
    async def heartbeat(
        db: AsyncSession,
        monitor_id: str,
    ) -> Monitor:

        monitor = await db.get(Monitor, monitor_id)

        if not monitor:
            raise MonitorNotFoundError(
                f"Monitor {monitor_id} not found."
            )

        now = utc_now()

        if monitor.status == "DOWN":
            raise MonitorStateError(
                "Monitor is DOWN. Manual recovery is required."
            )

        if monitor.status == "ACTIVE":
            expires_at = normalize_utc(monitor.expires_at)

            if now >= expires_at:
                monitor.status = "DOWN"
                monitor.alerted_at = now

                await db.commit()

                trigger_alert(monitor)

                raise MonitorExpiredError(
                    f"Monitor {monitor_id} has expired."
                )

        # A heartbeat resets the timer.
        # If PAUSED, it also automatically resumes monitoring.

        monitor.status = "ACTIVE"
        monitor.last_heartbeat_at = now
        monitor.expires_at = now + timedelta(
            seconds=monitor.timeout
        )
        monitor.remaining_seconds = None

        await db.commit()
        await db.refresh(monitor)

        return monitor

    @staticmethod
    async def pause(
        db: AsyncSession,
        monitor_id: str,
    ) -> Monitor:

        monitor = await db.get(Monitor, monitor_id)

        if not monitor:
            raise MonitorNotFoundError(
                f"Monitor {monitor_id} not found."
            )

        if monitor.status == "DOWN":
            raise MonitorStateError(
                "Cannot pause a DOWN monitor."
            )

        if monitor.status == "PAUSED":
            raise MonitorStateError(
                "Monitor is already paused."
            )

        now = utc_now()

        expires_at = normalize_utc(monitor.expires_at)

        if now >= expires_at:
            monitor.status = "DOWN"
            monitor.alerted_at = now

            await db.commit()

            trigger_alert(monitor)

            raise MonitorExpiredError(
                f"Monitor {monitor_id} has expired."
            )

        remaining = max(
            0.0,
            (expires_at - now).total_seconds()
        )

        monitor.status = "PAUSED"
        monitor.remaining_seconds = remaining

        await db.commit()
        await db.refresh(monitor)

        return monitor

    @staticmethod
    async def get_monitor(
        db: AsyncSession,
        monitor_id: str,
    ) -> Monitor:

        monitor = await db.get(Monitor, monitor_id)

        if not monitor:
            raise MonitorNotFoundError(
                f"Monitor {monitor_id} not found."
            )

        return monitor
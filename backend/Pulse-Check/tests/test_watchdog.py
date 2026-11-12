import pytest

from datetime import datetime, timedelta, timezone

from app.database.models import Monitor
from app.services.watchdog import Watchdog


@pytest.mark.asyncio
async def test_watchdog_detects_expired_monitor(
    client,
    test_session_factory,
    monkeypatch,
):

    from app.services import watchdog as watchdog_module

    alerts = []

    monkeypatch.setattr(
        watchdog_module,
        "trigger_alert",
        lambda monitor: alerts.append(monitor.id),
    )

    payload = {
        "id": "expired-device",
        "timeout": 60,
        "alert_email": "admin@critmon.com",
    }

    await client.post("/monitors", json=payload)

    # Force expiration

    async with test_session_factory() as db:

        monitor = await db.get(
            Monitor,
            "expired-device",
        )

        monitor.expires_at = (
            datetime.now(timezone.utc) - timedelta(seconds=10)
        )

        await db.commit()

    watchdog = Watchdog(
        interval=1.0,
        session_factory=test_session_factory,
    )

    await watchdog.check_expired_monitors()

    async with test_session_factory() as db:

        monitor = await db.get(
            Monitor,
            "expired-device",
        )

        assert monitor.status == "DOWN"
        assert monitor.alerted_at is not None

    assert alerts == ["expired-device"]


@pytest.mark.asyncio
async def test_watchdog_does_not_trigger_duplicate_alerts(
    client,
    test_session_factory,
    monkeypatch,
):

    from app.services import watchdog as watchdog_module

    alerts = []

    monkeypatch.setattr(
        watchdog_module,
        "trigger_alert",
        lambda monitor: alerts.append(monitor.id),
    )

    payload = {
        "id": "device-duplicate-test",
        "timeout": 60,
        "alert_email": "admin@critmon.com",
    }

    await client.post("/monitors", json=payload)

    async with test_session_factory() as db:

        monitor = await db.get(
            Monitor,
            "device-duplicate-test",
        )

        monitor.expires_at = (
            datetime.now(timezone.utc) - timedelta(seconds=10)
        )

        await db.commit()

    watchdog = Watchdog(
        session_factory=test_session_factory,
    )

    # First execution: triggers an alert.

    await watchdog.check_expired_monitors()

    # Second execution: should not trigger another alert.

    await watchdog.check_expired_monitors()

    assert alerts == ["device-duplicate-test"]


@pytest.mark.asyncio
async def test_watchdog_ignores_paused_monitor(
    client,
    test_session_factory,
    monkeypatch,
):

    from app.services import watchdog as watchdog_module

    alerts = []

    monkeypatch.setattr(
        watchdog_module,
        "trigger_alert",
        lambda monitor: alerts.append(monitor.id),
    )

    payload = {
        "id": "paused-device",
        "timeout": 60,
        "alert_email": "admin@critmon.com",
    }

    await client.post("/monitors", json=payload)

    await client.post(
        "/monitors/paused-device/pause"
    )

    # Move the expiration timestamp into the past
    async with test_session_factory() as db:

        monitor = await db.get(
            Monitor,
            "paused-device",
        )

        monitor.expires_at = (
            datetime.now(timezone.utc) - timedelta(seconds=10)
        )

        await db.commit()

    watchdog = Watchdog(
        session_factory=test_session_factory,
    )

    await watchdog.check_expired_monitors()

    async with test_session_factory() as db:

        monitor = await db.get(
            Monitor,
            "paused-device",
        )

        assert monitor.status == "PAUSED"

    assert alerts == []
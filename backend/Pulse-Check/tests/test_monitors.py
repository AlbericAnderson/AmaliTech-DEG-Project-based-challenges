import pytest

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database.models import Monitor


@pytest.mark.asyncio
async def test_health_endpoint(client):

    response = await client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "healthy"
    assert data["database"] == "connected"


@pytest.mark.asyncio
async def test_register_monitor(client):

    payload = {
        "id": "device-123",
        "timeout": 60,
        "alert_email": "admin@critmon.com",
    }

    response = await client.post(
        "/monitors",
        json=payload,
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] == "device-123"
    assert data["timeout"] == 60
    assert data["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_duplicate_registration(client):

    payload = {
        "id": "device-123",
        "timeout": 60,
        "alert_email": "admin@critmon.com",
    }

    first = await client.post("/monitors", json=payload)
    second = await client.post("/monitors", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_invalid_monitor_data(client):

    payload = {
        "id": "device-123",
        "timeout": -10,
        "alert_email": "invalid-email",
    }

    response = await client.post(
        "/monitors",
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_monitor(client):

    payload = {
        "id": "device-123",
        "timeout": 60,
        "alert_email": "admin@critmon.com",
    }

    await client.post("/monitors", json=payload)

    response = await client.get(
        "/monitors/device-123"
    )

    assert response.status_code == 200
    assert response.json()["id"] == "device-123"


@pytest.mark.asyncio
async def test_get_nonexistent_monitor(client):

    response = await client.get(
        "/monitors/unknown-device"
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_heartbeat_resets_expiration(client):

    payload = {
        "id": "device-123",
        "timeout": 60,
        "alert_email": "admin@critmon.com",
    }

    await client.post("/monitors", json=payload)

    before = await client.get("/monitors/device-123")

    response = await client.post(
        "/monitors/device-123/heartbeat"
    )

    after = await client.get("/monitors/device-123")

    assert response.status_code == 200

    old_expiration = datetime.fromisoformat(
        before.json()["expires_at"]
    )

    new_expiration = datetime.fromisoformat(
        after.json()["expires_at"]
    )

    assert new_expiration > old_expiration


@pytest.mark.asyncio
async def test_heartbeat_unknown_monitor(client):

    response = await client.post(
        "/monitors/unknown-device/heartbeat"
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_pause_monitor(client):

    payload = {
        "id": "device-123",
        "timeout": 60,
        "alert_email": "admin@critmon.com",
    }

    await client.post("/monitors", json=payload)

    response = await client.post(
        "/monitors/device-123/pause"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "PAUSED"


@pytest.mark.asyncio
async def test_heartbeat_resumes_paused_monitor(client):

    payload = {
        "id": "device-123",
        "timeout": 60,
        "alert_email": "admin@critmon.com",
    }

    await client.post("/monitors", json=payload)

    await client.post(
        "/monitors/device-123/pause"
    )

    response = await client.post(
        "/monitors/device-123/heartbeat"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_pause_already_paused_monitor(client):

    payload = {
        "id": "device-123",
        "timeout": 60,
        "alert_email": "admin@critmon.com",
    }

    await client.post("/monitors", json=payload)

    await client.post(
        "/monitors/device-123/pause"
    )

    response = await client.post(
        "/monitors/device-123/pause"
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_pause_unknown_monitor(client):

    response = await client.post(
        "/monitors/unknown-device/pause"
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_expired_monitor_rejects_heartbeat(
    client,
    test_session_factory,
    monkeypatch,
):

    from app.services import monitor as monitor_service

    alerts = []

    monkeypatch.setattr(
        monitor_service,
        "trigger_alert",
        lambda monitor: alerts.append(monitor.id),
    )

    payload = {
        "id": "device-123",
        "timeout": 60,
        "alert_email": "admin@critmon.com",
    }

    await client.post("/monitors", json=payload)

    async with test_session_factory() as db:

        monitor = await db.get(Monitor, "device-123")

        monitor.expires_at = (
            datetime.now(timezone.utc) - timedelta(seconds=5)
        )

        await db.commit()

    response = await client.post(
        "/monitors/device-123/heartbeat"
    )

    assert response.status_code == 409

    status_response = await client.get(
        "/monitors/device-123"
    )

    assert status_response.json()["status"] == "DOWN"
    assert alerts == ["device-123"]
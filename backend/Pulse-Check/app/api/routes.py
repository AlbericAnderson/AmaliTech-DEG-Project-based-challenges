from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database import get_db
from app.schemas.monitor import (
    MonitorCreate,
    MonitorResponse,
    HeartbeatResponse,
    PauseResponse,
)
from app.services.monitor import (
    MonitorService,
    MonitorNotFoundError,
    MonitorAlreadyExistsError,
    MonitorExpiredError,
    MonitorStateError,
)


router = APIRouter()


@router.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "application": "Pulse Check API",
    }


@router.post(
    "/monitors",
    response_model=MonitorResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Monitors"],
)
async def create_monitor(
    data: MonitorCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await MonitorService.register(db, data)

    except MonitorAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )


@router.post(
    "/monitors/{monitor_id}/heartbeat",
    response_model=HeartbeatResponse,
    tags=["Monitors"],
)
async def heartbeat(
    monitor_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        monitor = await MonitorService.heartbeat(
            db,
            monitor_id,
        )

        return HeartbeatResponse(
            message="Heartbeat received successfully.",
            id=monitor.id,
            status=monitor.status,
            expires_at=monitor.expires_at,
        )

    except MonitorNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except (
        MonitorExpiredError,
        MonitorStateError,
    ) as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )


@router.post(
    "/monitors/{monitor_id}/pause",
    response_model=PauseResponse,
    tags=["Monitors"],
)
async def pause_monitor(
    monitor_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        monitor = await MonitorService.pause(
            db,
            monitor_id,
        )

        return PauseResponse(
            message="Monitoring paused successfully.",
            id=monitor.id,
            status=monitor.status,
            remaining_seconds=monitor.remaining_seconds,
        )

    except MonitorNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except (
        MonitorExpiredError,
        MonitorStateError,
    ) as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )


@router.get(
    "/monitors/{monitor_id}",
    response_model=MonitorResponse,
    tags=["Monitors"],
)
async def get_monitor(
    monitor_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await MonitorService.get_monitor(
            db,
            monitor_id,
        )

    except MonitorNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )
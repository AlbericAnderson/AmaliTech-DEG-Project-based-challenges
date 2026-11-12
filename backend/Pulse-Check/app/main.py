import asyncio
import logging

from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings
from app.database.database import engine, init_db
from app.services.watchdog import watchdog


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):

    logger = logging.getLogger(__name__)

    logger.info("Starting Pulse Check API...")

    # Initialize database

    await init_db()

    logger.info("Database initialized.")

    # Start watchdog

    watchdog_task = asyncio.create_task(
        watchdog.run(),
        name="pulse-check-watchdog",
    )

    logger.info("Watchdog background task started.")

    yield

    # Stop watchdog

    logger.info("Shutting down Pulse Check API...")

    watchdog_task.cancel()

    with suppress(asyncio.CancelledError):
        await watchdog_task

    # Dispose database engine

    await engine.dispose()

    logger.info("Application shutdown complete.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.include_router(router)
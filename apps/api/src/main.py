from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager

from api import health_router, v1_router
from config.settings import Settings, get_settings
from handler import exception_handler
from logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings: Settings = get_settings()
    logger.info(f"Loaded API profile: {settings.profile}")
    yield


app = FastAPI(
    title="Engineering Knowledge Advisor API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(v1_router)

exception_handler.register(app)

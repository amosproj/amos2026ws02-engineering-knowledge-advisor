from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncEngine

from api import (
    health_router,
    v1_files_router,
    v1_ontology_router,
    v1_records_router,
    llm_router,
)
from config.settings import Settings, get_settings
from db.session import (
    create_catalog_service,
    create_engine,
    create_ograg_service,
    create_sessionmaker,
)
from handler import exception_handler, service_exception_handler
from logger import logger
from services.llm import LLMService

LOG_PROFILE: str = "Loaded API profile: {profile}"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # missing database URL or malformed ontology throws and stops startup
    settings: Settings = get_settings()
    logger.info(LOG_PROFILE.format(profile=settings.profile))

    engine: AsyncEngine = create_engine(settings)
    app.state.sessions = create_sessionmaker(engine)
    app.state.ograg = create_ograg_service(settings, engine)
    app.state.llm = LLMService(settings)
    app.state.catalog = create_catalog_service(settings, app.state.ograg)
    try:
        yield
    finally:
        await app.state.llm.close()
        await engine.dispose()


app = FastAPI(
    title="Engineering Knowledge Advisor API",
    version="0.2.1",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(v1_records_router)
app.include_router(v1_files_router)
app.include_router(v1_ontology_router)
app.include_router(llm_router)

exception_handler.register(app)
service_exception_handler.register(app)

from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncEngine

from api import basic_router, health_router, v1_catalog_router, v1_records_router
from config.settings import Settings, get_settings
from db import create_engine, create_sessionmaker, get_ograg_tables
from handler import exception_handler, service_exception_handler
from logger import logger
from services.ograg.ontology import Ontology
from services.ograg.service import OgRagService
from services.postgres.record_store import PgRecordStore

LOG_PROFILE: str = "Loaded API profile: {profile}"
LOG_ONTOLOGY: str = "Loaded ontology {path} version {version}"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # missing database URL or malformed ontology throws and stops startup
    settings: Settings = get_settings()
    logger.info(LOG_PROFILE.format(profile=settings.profile))

    engine: AsyncEngine = create_engine(settings)
    app.state.sessions = create_sessionmaker(engine)

    ontology = Ontology.load(settings.ograg_ontology_path)
    store = PgRecordStore(
        engine,
        tables=get_ograg_tables(),
        identity_property_names=ontology.get_identity_property_names(),
    )
    app.state.ograg = OgRagService(ontology, store)

    logger.info(
        LOG_ONTOLOGY.format(path=settings.ograg_ontology_path, version=ontology.version)
    )
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(
    title="Engineering Knowledge Advisor API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(basic_router)
app.include_router(v1_records_router)
app.include_router(v1_catalog_router)

exception_handler.register(app)
service_exception_handler.register(app)

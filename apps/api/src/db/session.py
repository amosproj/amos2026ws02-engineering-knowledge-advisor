from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config.settings import Settings
from db.model_base import get_ograg_tables
from logger import logger
from services import LLMService
from services.catalog import CatalogService
from services.llm.service import ConfiguredLLMService
from services.ograg.ontology import Ontology
from services.ograg.service import OgRagService
from services.postgres.record_store import PgRecordStore
from services.postgres.upload_store import PgUploadStore
from services.s3 import S3ObjectStorage

ERROR_NO_DATABASE_URL: str = "API_DATABASE_URL is not set"
LOG_ONTOLOGY: str = "Loaded ontology {path} version {version}"


def get_database_url(settings: Settings) -> str:
    """
    Raises:
        ValueError: ``API_DATABASE_URL`` is not set.
    """
    if settings.database_url is None:
        raise ValueError(ERROR_NO_DATABASE_URL)
    return settings.database_url.get_secret_value()


def create_engine(settings: Settings) -> AsyncEngine:
    """The app's async engine. One per process.

    Raises:
        ValueError: ``API_DATABASE_URL`` is not set.
    """
    return create_async_engine(get_database_url(settings), pool_pre_ping=True)


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncGenerator[AsyncSession]:
    """Request's unit of work, an ``AsyncSession`` inside ``session.begin()``.

    Commits when route returns, rolls back when it raises.
    Use with ``Depends(get_session, scope="function")``: commits before response is sent => failing commit errors out
    """
    sessions: async_sessionmaker[AsyncSession] = request.app.state.sessions
    async with sessions() as session, session.begin():
        yield session


def create_ograg_service(settings: Settings, engine: AsyncEngine) -> OgRagService:
    """The OG-RAG service on ``engine``. One per process.

    Raises:
        OSError, json.JSONDecodeError, OntologyError: the ontology cannot be read or is malformed.
    """
    ontology = Ontology.load(settings.ograg_ontology_path)
    store = PgRecordStore(
        engine,
        tables=get_ograg_tables(),
        identity_property_names=ontology.get_identity_property_names(),
    )
    logger.info(
        LOG_ONTOLOGY.format(path=settings.ograg_ontology_path, version=ontology.version)
    )
    return OgRagService(ontology, store)


def create_catalog_service(settings: Settings, ograg: OgRagService) -> CatalogService:
    """The catalog on ``ograg``, with the upload state in Postgres and the files in S3. One per process."""
    return CatalogService(
        ograg,
        PgUploadStore(get_ograg_tables()),
        S3ObjectStorage(settings),
    )


def create_llm_service(settings: Settings) -> LLMService:
    """The LLM service. One per process."""
    return ConfiguredLLMService(settings)

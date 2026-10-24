import logging

from api import health_router, v1_router
from fastapi import FastAPI

app = FastAPI(
    title="Engineering Knowledge Advisor API",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(v1_router)


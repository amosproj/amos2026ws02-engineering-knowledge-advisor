import json
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.responses import StreamingResponse

from api.router_builder import ApiRouterBuilder
from model.problem import Problem
from services.llm import LLMService
from services.llm_impl import (
    ChatRequest,
    ChatResponse,
    ModelInfo,
    ProviderInfo,
)
from services.llm_impl.errors import LLMError

RESPONSE_DETAIL_422: str = "Request validation failed."

llm_router = ApiRouterBuilder().version("v1").add_tags(["llm"]).build()


class ServerSentEventResponse(StreamingResponse):
    media_type = "text/event-stream"


def get_llm_service(request: Request) -> LLMService:
    return request.app.state.llm


LLM = Annotated[LLMService, Depends(get_llm_service)]


@llm_router.post(
    "/llm/chat",
    responses={
        400: {"model": Problem, "description": "Invalid provider or model."},
        422: {"model": Problem, "description": RESPONSE_DETAIL_422},
        429: {"model": Problem, "description": "Provider rate limit reached."},
        502: {"model": Problem, "description": "Provider request failed."},
        503: {"model": Problem, "description": "Provider is unavailable."},
        504: {"model": Problem, "description": "Provider request timed out."},
    },
)
async def chat(body: ChatRequest, llm: LLM) -> ChatResponse:
    return await llm.complete(body)


@llm_router.post(
    "/llm/chat/stream",
    response_class=ServerSentEventResponse,
    responses={
        400: {"model": Problem, "description": "Invalid provider or model."},
        422: {"model": Problem, "description": RESPONSE_DETAIL_422},
        429: {"model": Problem, "description": "Provider rate limit reached."},
        502: {"model": Problem, "description": "Provider request failed."},
        503: {"model": Problem, "description": "Provider is unavailable."},
        504: {"model": Problem, "description": "Provider request timed out."},
    },
)
async def chat_stream(body: ChatRequest, llm: LLM) -> ServerSentEventResponse:
    async def events() -> AsyncGenerator[str]:
        try:
            async for chunk in llm.stream(body):
                yield f"data: {chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"
        except LLMError as exc:
            payload: str = json.dumps(
                {"error": {"code": exc.error_code, "detail": exc.detail}}
            )
            yield f"event: error\ndata: {payload}\n\n"

    return ServerSentEventResponse(
        events(),
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@llm_router.get("/llm/providers")
async def providers(llm: LLM) -> list[ProviderInfo]:
    return llm.list_providers()


@llm_router.get(
    "/llm/models",
    responses={422: {"model": Problem, "description": RESPONSE_DETAIL_422}},
)
async def models(
    llm: LLM,
    provider: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
) -> list[ModelInfo]:
    return await llm.list_models(provider)

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

MessageRole = Literal["system", "user", "assistant"]
ResponseFormat = Literal["text", "json_object"]
MAX_PROMPT_CHARACTERS: int = 128_000


class ChatMessage(BaseModel):
    role: MessageRole
    content: Annotated[str, Field(min_length=1, max_length=32_000)]


class ChatRequest(BaseModel):
    provider: Annotated[str | None, Field(default=None, min_length=1, max_length=40)]
    model: Annotated[str | None, Field(default=None, min_length=1, max_length=200)]
    messages: Annotated[list[ChatMessage], Field(min_length=1, max_length=100)]
    temperature: Annotated[float | None, Field(default=None, ge=0, le=2)]
    max_tokens: Annotated[int, Field(default=1024, ge=1, le=32_768)]
    top_p: Annotated[float | None, Field(default=None, ge=0, le=1)]
    response_format: ResponseFormat = "text"

    @model_validator(mode="after")
    def validate_prompt(self) -> Self:
        if not any(message.role == "user" for message in self.messages):
            raise ValueError("At least one user message is required")
        conversation_started: bool = False
        for message in self.messages:
            if message.role == "system" and conversation_started:
                raise ValueError("System messages must precede conversation messages")
            conversation_started = conversation_started or message.role != "system"
        if (
            sum(len(message.content) for message in self.messages)
            > MAX_PROMPT_CHARACTERS
        ):
            raise ValueError("The combined message content is too large")
        return self


class TokenUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ChatResponse(BaseModel):
    provider: str
    model: str
    content: str
    finish_reason: str | None = None
    usage: TokenUsage | None = None
    request_id: str


class ChatStreamChunk(BaseModel):
    provider: str
    model: str
    content: str = ""
    finish_reason: str | None = None
    usage: TokenUsage | None = None


class ProviderInfo(BaseModel):
    name: str
    default_model: str | None


class ModelInfo(BaseModel):
    provider: str
    model: str

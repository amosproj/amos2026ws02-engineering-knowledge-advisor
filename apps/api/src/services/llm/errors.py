class LLMError(Exception):
    status_code: int = 502
    error_code: str = "llm_provider_error"
    detail: str = "The LLM provider could not complete the request."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.detail
        super().__init__(self.detail)


class InvalidProviderError(LLMError):
    status_code = 400
    error_code = "invalid_provider"
    detail = "The requested LLM provider is not supported."


class ProviderDisabledError(LLMError):
    status_code = 503
    error_code = "provider_disabled"
    detail = "The requested LLM provider is not enabled."


class UnsupportedModelError(LLMError):
    status_code = 400
    error_code = "unsupported_model"
    detail = "The requested model is not available from the selected provider."


class InvalidLLMRequestError(LLMError):
    status_code = 422
    error_code = "invalid_llm_request"
    detail = "The LLM provider rejected the request."


class ContextLengthError(LLMError):
    status_code = 413
    error_code = "context_length_exceeded"
    detail = "The request exceeds the model's context limit."


class ProviderAuthenticationError(LLMError):
    status_code = 502
    error_code = "provider_authentication_failed"
    detail = "The configured LLM provider credentials were rejected."


class ProviderRateLimitError(LLMError):
    status_code = 429
    error_code = "provider_rate_limited"
    detail = "The LLM provider rate limit was reached."


class ProviderTimeoutError(LLMError):
    status_code = 504
    error_code = "provider_timeout"
    detail = "The LLM provider request timed out."


class ProviderUnavailableError(LLMError):
    status_code = 503
    error_code = "provider_unavailable"
    detail = "The LLM provider is temporarily unavailable."


class StreamingInterruptedError(LLMError):
    status_code = 502
    error_code = "stream_interrupted"
    detail = "The LLM provider stream was interrupted."

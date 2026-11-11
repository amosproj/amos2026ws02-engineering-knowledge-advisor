# LLM integration

The backend exposes a single provider-independent chat interface at `/api/v1/llm`.
Application code uses `LLMService` and normalized Pydantic models; provider SDK
types are not part of the API. Provider communication uses the provider HTTP APIs
through the backend's shared async HTTP client.

## Architecture

- `services/llm/models.py` defines validated chat, usage, response, and provider
  metadata models.
- `services/llm/providers.py` adapts OpenAI, Anthropic, Google Gemini, Mistral,
  Ollama, Azure OpenAI, and Hetzner Inference HTTP APIs to the `LLMProvider`
  protocol.
- `services/llm/service.py` resolves enabled providers and models and provides
  completion, streaming, and model-list operations.
- `api/router_llm.py` exposes the service through FastAPI and encodes stream events
  as Server-Sent Events (SSE).
- Provider settings use `SecretStr`, and credentials are only used by the backend.
  Prompts and credentials are not logged.
- Docker Compose passes LLM credentials only to the API service, not migration or
  CAD-worker containers.

Provider adapters are enabled individually and can be used simultaneously. The
API does not silently select a model: send one in the request or configure that
provider's `DEFAULT_MODEL`. `LLM_DEFAULT_PROVIDER` is optional.

## Configuration

All settings use the existing `API_` environment prefix. Provider-specific values
are nested with `__`:

| Provider          | Environment variables                                                                                                                                                                                               |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| OpenAI            | `API_LLM_OPENAI__ENABLED`, `API_LLM_OPENAI__API_KEY`, `API_LLM_OPENAI__BASE_URL`, `API_LLM_OPENAI__DEFAULT_MODEL`, `API_LLM_OPENAI__TIMEOUT_SECONDS`, `API_LLM_OPENAI__OPTIONS`                                     |
| Anthropic         | `API_LLM_ANTHROPIC__ENABLED`, `API_LLM_ANTHROPIC__API_KEY`, `API_LLM_ANTHROPIC__BASE_URL`, `API_LLM_ANTHROPIC__DEFAULT_MODEL`, `API_LLM_ANTHROPIC__TIMEOUT_SECONDS`, `API_LLM_ANTHROPIC__OPTIONS`                   |
| Google Gemini     | `API_LLM_GOOGLE__ENABLED`, `API_LLM_GOOGLE__API_KEY`, `API_LLM_GOOGLE__BASE_URL`, `API_LLM_GOOGLE__DEFAULT_MODEL`, `API_LLM_GOOGLE__TIMEOUT_SECONDS`, `API_LLM_GOOGLE__OPTIONS`                                     |
| Mistral           | `API_LLM_MISTRAL__ENABLED`, `API_LLM_MISTRAL__API_KEY`, `API_LLM_MISTRAL__BASE_URL`, `API_LLM_MISTRAL__DEFAULT_MODEL`, `API_LLM_MISTRAL__TIMEOUT_SECONDS`, `API_LLM_MISTRAL__OPTIONS`                               |
| Ollama            | `API_LLM_OLLAMA__ENABLED`, `API_LLM_OLLAMA__BASE_URL`, `API_LLM_OLLAMA__DEFAULT_MODEL`, `API_LLM_OLLAMA__TIMEOUT_SECONDS`, `API_LLM_OLLAMA__OPTIONS`                                                                |
| Azure OpenAI      | `API_LLM_AZURE_OPENAI__ENABLED`, `API_LLM_AZURE_OPENAI__API_KEY`, `API_LLM_AZURE_OPENAI__BASE_URL`, `API_LLM_AZURE_OPENAI__DEFAULT_MODEL`, `API_LLM_AZURE_OPENAI__TIMEOUT_SECONDS`, `API_LLM_AZURE_OPENAI__OPTIONS` |
| Hetzner Inference | `API_LLM_HETZNER__ENABLED`, `API_LLM_HETZNER__API_KEY`, `API_LLM_HETZNER__BASE_URL`, `API_LLM_HETZNER__DEFAULT_MODEL`, `API_LLM_HETZNER__TIMEOUT_SECONDS`, `API_LLM_HETZNER__OPTIONS`                               |

Set `API_LLM_DEFAULT_PROVIDER` to a supported, enabled provider to use it when the
request omits `provider`. The provider `DEFAULT_MODEL` is the fallback when the
request omits `model`. Standard provider base URLs are used if `BASE_URL` is
omitted, except Azure OpenAI, which requires its resource URL. Ollama does not
require an API key. `OPTIONS` accepts a JSON object of provider-specific options;
Azure's `api_version` option defaults to `2024-10-21`.
Hetzner defaults to `https://inference.hetzner.com/api/v1` and uses a bearer
token. Its model list is queried from the provider's `/models` endpoint.

Hetzner describes Inference as experimental and does not guarantee availability
or performance; it is not intended for production environments. Review
[Hetzner's Inference documentation](https://docs.hetzner.com/general/company-and-policy/experiments/inference/)
and applicable model licenses before use. The provider currently documents
`Qwen/Qwen3.6-35B-A3B-FP8` and `Qwen3.8-27B`, but the live `/models` response is
the definitive list and can change.

When the API runs in Docker Desktop on Windows or macOS and Ollama runs directly
on the host, set `API_LLM_OLLAMA__BASE_URL=http://host.docker.internal:11434`.
`localhost` inside the API container refers to that container, not the host. On
Linux, use a reachable Ollama service/container hostname or configure a host
gateway explicitly.

For example, configure OpenAI with:

```dotenv
API_LLM_DEFAULT_PROVIDER=openai
API_LLM_OPENAI__ENABLED=true
API_LLM_OPENAI__API_KEY=<secret-from-your-secret-store>
API_LLM_OPENAI__DEFAULT_MODEL=gpt-4o-mini
```

To configure Google Gemini instead, set its API key, model, and optionally make
it the default provider:

```dotenv
API_LLM_DEFAULT_PROVIDER=google
API_LLM_GOOGLE__ENABLED=true
API_LLM_GOOGLE__API_KEY=<secret-from-your-secret-store>
API_LLM_GOOGLE__DEFAULT_MODEL=gemini-2.0-flash
```

To use Hetzner instead, set its token and model and select it as the default:

```dotenv
API_LLM_DEFAULT_PROVIDER=hetzner
API_LLM_HETZNER__ENABLED=true
API_LLM_HETZNER__API_KEY=<secret-from-your-secret-store>
API_LLM_HETZNER__DEFAULT_MODEL=Qwen/Qwen3.6-35B-A3B-FP8
```

Never put production API keys in `.env.example`, source control, or client-side
configuration. Use deployment secrets and inject them as environment variables.

## Endpoints

All routes are under `/api/v1`:

| Method and path                   | Behavior                                                       |
| --------------------------------- | -------------------------------------------------------------- |
| `POST /llm/chat`                  | Generate a normalized chat completion                          |
| `POST /llm/chat/stream`           | Stream normalized chunks as SSE                                |
| `GET /llm/providers`              | Return enabled providers and their configured default model    |
| `GET /llm/models?provider=openai` | Fetch provider models where available                          |
| `GET /llm/models`                 | Return configured default models without making upstream calls |

Chat requests accept `system`, `user`, and `assistant` messages; optional
`provider`, `model`, `temperature` (`0`–`2`), `max_tokens`, `top_p` (`0`–`1`),
and `response_format` (`text` or `json_object`). System messages must precede
conversation history. The service limits requests to 100 messages, 32,000
characters per message, 128,000 combined prompt characters, and 32,768 requested
output tokens.

```sh
curl http://localhost:8000/api/v1/llm/chat \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "openai",
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "system", "content": "Answer concisely."},
      {"role": "user", "content": "What is a bearing?"}
    ],
    "temperature": 0.2,
    "max_tokens": 300
  }'
```

With Hetzner enabled and configured, the same request contract applies:

```sh
curl http://localhost:8080/api/v1/llm/chat \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "hetzner",
    "model": "Qwen/Qwen3.6-35B-A3B-FP8",
    "messages": [{"role": "user", "content": "Explain a gear train."}]
  }'
```

Google Gemini uses the same provider-neutral chat endpoint:

```sh
curl http://localhost:8080/api/v1/llm/chat \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "google",
    "model": "gemini-3.6-flash",
    "messages": [{"role": "user", "content": "Explain a gear train."}]
  }'
```

Ollama uses the same provider-neutral chat endpoint:

```sh
curl -N http://localhost:8080/api/v1/llm/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "ollama",
    "model": "llama3.1:latest",
    "messages": [{"role": "user", "content": "Explain a gear train."}]
  }'
```

Make sure the model is installed in Ollama first, for example with
`ollama pull llama3.2`. The requested model must match an installed Ollama model
tag.

Each stream event is `data: <JSON>\n\n` with `provider`, `model`, `content`, and
optional `finish_reason` and `usage`. The normal end marker is
`data: [DONE]\n\n`. An upstream failure after streaming starts is sent as an
`event: error` with a safe application error code and detail. Disconnecting the
client cancels the upstream stream. Finish reasons are normalized to `stop`,
`length`, `content_filter`, or `tool_calls` when recognized; unknown values are
lowercased and preserved.

## Errors and reliability

Non-streaming errors follow the application's RFC 9457 `application/problem+json`
format and include an `errorCode` extension. Common codes include
`invalid_provider`, `provider_disabled`, `unsupported_model`,
`provider_authentication_failed`, `provider_rate_limited`, `provider_timeout`,
`provider_unavailable`, `invalid_llm_request`, and `context_length_exceeded`.
Upstream messages and credentials are not returned.

Provider timeouts are configurable. Automatic retries are intentionally not
performed for generation requests: replaying a timed-out request can generate
duplicate work and charges. The application currently has no authentication or
rate-limiting middleware; the LLM endpoints inherit that existing API behavior.
Deploy behind the application's trusted access boundary and apply rate limits
before exposing these routes to untrusted clients.

## Adding a provider

1. Implement `LLMProvider` in `services/llm/providers.py`, normalizing completion,
   model-list, stream chunks, and upstream errors to the existing LLM models.
2. Add its `LLMProviderSettings` field and name mapping in `Settings`.
3. Register its adapter in `_PROVIDER_TYPES` in `services/llm/service.py`.
4. Add mocked HTTP tests for request mapping, normalization, errors, streaming,
   and model listing. Do not call provider services in automated tests.

The application depends only on `LLMService` and normalized model types; endpoint
and business logic do not depend on provider-specific APIs.

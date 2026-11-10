from services.llm.models import ChatRequest
from services.llm.providers.openai import OpenAIProvider
from services.llm.providers.utils import model_path


class AzureOpenAIProvider(OpenAIProvider):
    name = "azure_openai"
    default_base_url = ""

    def completions_url(self, model: str) -> str:
        version: str = str(self.config.options.get("api_version", "2024-10-21"))
        return (
            f"{self._base_url(self.default_base_url)}/openai/deployments/{model_path(model)}"
            f"/chat/completions?api-version={version}"
        )

    def _request_payload(self, request: ChatRequest, model: str) -> dict[str, object]:
        payload: dict[str, object] = super()._request_payload(request, model)
        payload.pop("model", None)
        payload.pop("api_version", None)
        return payload

    def completion_headers(self) -> dict[str, str]:
        if self.config.api_key is None:
            return {}
        return {"api-key": self.config.api_key.get_secret_value()}

    async def list_models(self) -> list[str]:
        return [self.config.default_model] if self.config.default_model else []

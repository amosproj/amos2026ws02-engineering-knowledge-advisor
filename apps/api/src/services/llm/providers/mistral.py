from services.llm.providers.openai import OpenAIProvider


class MistralProvider(OpenAIProvider):
    name = "mistral"
    default_base_url = "https://api.mistral.ai/v1"

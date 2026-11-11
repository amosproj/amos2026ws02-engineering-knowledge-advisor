from services.llm.providers.openai import OpenAIProvider


class HetznerProvider(OpenAIProvider):
    name = "hetzner"
    default_base_url = "https://inference.hetzner.com/api/v1"
    default_max_tokens = 4096

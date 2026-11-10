from urllib.parse import quote


def sum_token_counts(prompt: object, completion: object) -> int | None:
    if isinstance(prompt, int) and isinstance(completion, int):
        return prompt + completion
    return None


def optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def model_path(model: str) -> str:
    return quote(model.removeprefix("models/"), safe="")


def supports_google_generate(model: dict[str, object]) -> bool:
    methods: object = model.get("supportedGenerationMethods")
    return isinstance(methods, list) and "generateContent" in methods

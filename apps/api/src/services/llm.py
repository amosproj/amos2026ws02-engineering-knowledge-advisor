from __future__ import annotations

from abc import abstractmethod
from typing import Any, Protocol


class LLMError(RuntimeError):
    """Provider failure, or unusable reply. Raise for timeouts, HTTP errors, refusals, truncated replies etc."""


class LLM(Protocol):
    """Generic LLM interface. Calls a LLM with JSON output.

    Attributes:
        name: provider plus model that's kept as provenance, e.g. ``"claude:claude-opus-5-5"``
    """

    name: str

    @abstractmethod
    async def generate_structured(
        self,
        system_prompt: str,
        user_message: str,
        schema: dict[str, Any],
        call_name: str,
    ) -> dict[str, Any]:
        """Calls model whose reply is a JSON matching ``schema``.

        Args:
            system_prompt: system prompt.
            user_message: user message.
            schema: JSON schema of the reply, strict-mode compatible (every property required, no extra properties).
            call_name: label for the call: ``"grounded_answer"``, ``"guideline_review"`` or ``"knowledge_extraction"`` (for logs, or as the schema name if required by provider).

        Returns:
            Parsed reply. Use provider's structured-output if available.

        Raises:
            LLMError: any provider failure, refusal, truncation or a reply that is not a JSON object.
        """
        ...

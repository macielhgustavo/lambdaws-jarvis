"""Model providers for Jarvis.

Provider details stay out of the agent runtime so models can be swapped without
rewriting tool dispatch, memory, UI, or client code.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

from groq import Groq


class ProviderUnavailable(RuntimeError):
    """Raised when a provider cannot answer the current request."""


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(slots=True)
class AssistantTurn:
    content: str
    tool_calls: list[ToolCall]


class GroqProvider:
    name = "Groq · GPT-OSS 120B"

    def __init__(self, api_key: str | None, model: str) -> None:
        self.model = model
        try:
            self.client = Groq(api_key=api_key) if api_key else None
        except (TypeError, ValueError, OSError):
            self.client = None

    @property
    def available(self) -> bool:
        return self.client is not None

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        reasoning_effort: str = "low",
    ) -> AssistantTurn:
        if self.client is None:
            raise ProviderUnavailable("Groq não configurado.")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                reasoning_effort=reasoning_effort,
            )
        except Exception as error:  # provider boundary
            raise ProviderUnavailable(str(error)) from error

        message = response.choices[0].message
        calls = [
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=call.function.arguments or "{}",
            )
            for call in (message.tool_calls or [])
        ]
        return AssistantTurn(content=message.content or "", tool_calls=calls)


class OllamaProvider:
    """Local model fallback.

    v11 keeps the existing text fallback behavior behind a provider boundary.
    Tool-capable local inference can now be added here without touching the
    agent runtime or desktop clients.
    """

    def __init__(self, model: str) -> None:
        self.model = model
        self.name = f"Ollama · {model}"

    def generate(self, prompt: str) -> str:
        try:
            output = subprocess.check_output(
                ["ollama", "run", self.model, prompt],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=180,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise ProviderUnavailable(str(error)) from error
        return output.strip()

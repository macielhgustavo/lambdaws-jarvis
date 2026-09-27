"""Provider-agnostic agent runtime for Jarvis."""

from __future__ import annotations

import json
from typing import Any, Callable

from .providers import GroqProvider, OllamaProvider, ProviderUnavailable
from .tools import ToolRegistry


HistorySaver = Callable[[list[dict[str, str]]], None]


class AgentRuntime:
    def __init__(
        self,
        *,
        system_prompt: str,
        cloud: GroqProvider,
        local: OllamaProvider,
        tools: ToolRegistry,
        history: list[dict[str, str]],
        save_history: HistorySaver,
        max_steps: int = 8,
        history_window: int = 24,
    ) -> None:
        self.system_prompt = system_prompt
        self.cloud = cloud
        self.local = local
        self.tools = tools
        self.history = history
        self._save_history = save_history
        self.max_steps = max_steps
        self.history_window = history_window

    def _fallback(self, prompt: str) -> tuple[str, str]:
        try:
            return self.local.generate(prompt), self.local.name
        except ProviderUnavailable as error:
            return f"Groq e Ollama indisponíveis: {error}", "offline"

    def ask(self, prompt: str) -> tuple[str, str]:
        prompt = str(prompt).strip()
        if not prompt:
            return "Escreva uma pergunta ou ordem para o Jarvis.", "local"

        if not self.cloud.available:
            return self._fallback(prompt)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            *self.history[-self.history_window :],
            {"role": "user", "content": prompt},
        ]

        try:
            for _ in range(self.max_steps):
                turn = self.cloud.complete(messages, self.tools.schemas())
                assistant_entry: dict[str, Any] = {
                    "role": "assistant",
                    "content": turn.content,
                }

                if turn.tool_calls:
                    assistant_entry["tool_calls"] = [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": call.arguments,
                            },
                        }
                        for call in turn.tool_calls
                    ]

                messages.append(assistant_entry)

                if not turn.tool_calls:
                    self.history.extend(
                        [
                            {"role": "user", "content": prompt},
                            {"role": "assistant", "content": turn.content},
                        ]
                    )
                    self._save_history(self.history)
                    return turn.content, self.cloud.name

                for call in turn.tool_calls:
                    try:
                        args = json.loads(call.arguments or "{}")
                    except (TypeError, ValueError):
                        args = {}

                    try:
                        result = self.tools.execute(call.name, args)
                    except Exception as error:  # tool isolation
                        result = {"error": str(error)}

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(
                                result,
                                ensure_ascii=False,
                                default=str,
                            ),
                        }
                    )

            return "Limite de etapas do agente atingido.", self.cloud.name
        except ProviderUnavailable:
            return self._fallback(prompt)

    def clear(self) -> None:
        self.history.clear()
        self._save_history([])

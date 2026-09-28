"""Model providers for Jarvis."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
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
        except Exception as error:
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
    """Tool-capable local provider backed by Ollama's chat API."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 180.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.name = f"Ollama · {model}"

    @property
    def available(self) -> bool:
        try:
            request = urllib.request.Request(
                self.base_url + "/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=1.5) as response:
                return response.status == 200
        except (OSError, urllib.error.URLError):
            return False

    def _native_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        native = []
        for message in messages:
            role = message.get("role")
            if role == "tool":
                native.append({"role": "tool", "content": message.get("content", "")})
                continue

            item = {
                "role": role,
                "content": message.get("content", ""),
            }
            if role == "assistant" and message.get("tool_calls"):
                calls = []
                for call in message["tool_calls"]:
                    function = call.get("function", {})
                    arguments = function.get("arguments", {})
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except ValueError:
                            arguments = {}
                    calls.append(
                        {
                            "function": {
                                "name": function.get("name", ""),
                                "arguments": arguments,
                            }
                        }
                    )
                item["tool_calls"] = calls
            native.append(item)
        return native

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        reasoning_effort: str = "low",
    ) -> AssistantTurn:
        del reasoning_effort
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._native_messages(messages),
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        request = urllib.request.Request(
            self.base_url + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, ValueError) as error:
            raise ProviderUnavailable(str(error)) from error

        message = data.get("message") or {}
        calls = []
        for index, call in enumerate(message.get("tool_calls") or []):
            function = call.get("function") or {}
            arguments = function.get("arguments", {})
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False)
            calls.append(
                ToolCall(
                    id=str(call.get("id") or f"ollama-{index}"),
                    name=str(function.get("name") or ""),
                    arguments=arguments,
                )
            )

        return AssistantTurn(
            content=str(message.get("content") or ""),
            tool_calls=[call for call in calls if call.name],
        )

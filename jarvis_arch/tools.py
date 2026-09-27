"""Tool registry used by every Jarvis client and provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


ToolHandler = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One executable capability exposed to the agent."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    category: str = "general"

    def as_provider_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Explicit registry replacing the monolithic execute_tool dispatcher."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Ferramenta já registrada: {spec.name}")
        self._tools[spec.name] = spec

    def register_schema(
        self,
        schema: dict[str, Any],
        handler: ToolHandler,
        *,
        category: str = "general",
    ) -> None:
        function = schema.get("function", {})
        self.register(
            ToolSpec(
                name=function["name"],
                description=function.get("description", ""),
                parameters=function.get(
                    "parameters",
                    {"type": "object", "properties": {}},
                ),
                handler=handler,
                category=category,
            )
        )

    def schemas(self) -> list[dict[str, Any]]:
        return [spec.as_provider_schema() for spec in self._tools.values()]

    def execute(self, name: str, args: dict[str, Any] | None = None) -> Any:
        try:
            spec = self._tools[name]
        except KeyError as error:
            raise KeyError(f"Ferramenta desconhecida: {name}") from error
        return spec.handler(**(args or {}))

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

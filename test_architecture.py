import unittest

from jarvis_arch.events import EventBus
from jarvis_arch.providers import AssistantTurn, ProviderUnavailable, ToolCall
from jarvis_arch.runtime import AgentRuntime
from jarvis_arch.tools import ToolRegistry, ToolSpec


class FakeCloud:
    name = "fake-cloud"

    def __init__(self, turns, available=True):
        self.turns = list(turns)
        self.available = available
        self.calls = []

    def complete(self, messages, tools, *, reasoning_effort="low"):
        self.calls.append(([dict(item) for item in messages], list(tools), reasoning_effort))
        if not self.turns:
            raise ProviderUnavailable("sem resposta")
        return self.turns.pop(0)


class FakeLocal:
    name = "fake-local"

    def __init__(self, answer="fallback"):
        self.answer = answer
        self.prompts = []

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self.answer


class ArchitectureTests(unittest.TestCase):
    def test_tool_registry_exposes_schema_and_executes_handler(self):
        registry = ToolRegistry()
        registry.register(
            ToolSpec(
                name="sum",
                description="soma dois números",
                parameters={
                    "type": "object",
                    "properties": {
                        "a": {"type": "integer"},
                        "b": {"type": "integer"},
                    },
                    "required": ["a", "b"],
                },
                handler=lambda a, b: {"value": a + b},
                category="test",
            )
        )
        self.assertEqual(registry.execute("sum", {"a": 2, "b": 3}), {"value": 5})
        self.assertEqual(registry.schemas()[0]["function"]["name"], "sum")
        self.assertEqual(registry.names(), ("sum",))

    def test_runtime_executes_tool_then_returns_final_answer(self):
        registry = ToolRegistry()
        registry.register(
            ToolSpec(
                name="echo",
                description="eco",
                parameters={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
                handler=lambda value: {"echo": value},
            )
        )
        cloud = FakeCloud(
            [
                AssistantTurn(
                    content="",
                    tool_calls=[ToolCall(id="1", name="echo", arguments='{"value":"oi"}')],
                ),
                AssistantTurn(content="feito", tool_calls=[]),
            ]
        )
        local = FakeLocal()
        saved = []
        runtime = AgentRuntime(
            system_prompt="system",
            cloud=cloud,
            local=local,
            tools=registry,
            history=[],
            save_history=lambda history: saved.append(list(history)),
        )

        answer, backend = runtime.ask("teste")

        self.assertEqual((answer, backend), ("feito", "fake-cloud"))
        self.assertEqual(runtime.history[-1]["content"], "feito")
        self.assertEqual(saved[-1][-2]["role"], "user")
        second_messages = cloud.calls[1][0]
        self.assertEqual(second_messages[-1]["role"], "tool")
        self.assertIn('"echo": "oi"', second_messages[-1]["content"])

    def test_runtime_falls_back_when_cloud_is_unavailable(self):
        runtime = AgentRuntime(
            system_prompt="system",
            cloud=FakeCloud([], available=False),
            local=FakeLocal("local-ok"),
            tools=ToolRegistry(),
            history=[],
            save_history=lambda _: None,
        )
        self.assertEqual(runtime.ask("oi"), ("local-ok", "fake-local"))

    def test_event_bus_subscribe_publish_and_unsubscribe(self):
        bus = EventBus()
        seen = []
        unsubscribe = bus.subscribe("voice.started", seen.append)
        bus.publish("voice.started", source="mic")
        unsubscribe()
        bus.publish("voice.started", source="mic2")
        self.assertEqual(seen, [{"source": "mic"}])


if __name__ == "__main__":
    unittest.main()

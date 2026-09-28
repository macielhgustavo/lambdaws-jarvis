import json
import unittest
from unittest.mock import patch

from jarvis_arch.providers import OllamaProvider


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class ProviderTests(unittest.TestCase):
    def test_ollama_parses_native_tool_call(self):
        provider = OllamaProvider("qwen3:4b")
        response = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "system_info",
                            "arguments": {},
                        }
                    }
                ],
            }
        }
        with patch(
            "jarvis_arch.providers.urllib.request.urlopen",
            return_value=FakeResponse(response),
        ) as urlopen:
            turn = provider.complete(
                [{"role": "user", "content": "como está o pc?"}],
                [
                    {
                        "type": "function",
                        "function": {
                            "name": "system_info",
                            "description": "info",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                ],
            )

        self.assertEqual(turn.tool_calls[0].name, "system_info")
        self.assertEqual(json.loads(turn.tool_calls[0].arguments), {})
        sent = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(sent["model"], "qwen3:4b")
        self.assertTrue(sent["tools"])

    def test_ollama_normalizes_openai_style_tool_history(self):
        provider = OllamaProvider("qwen3:4b")
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "abc",
                        "type": "function",
                        "function": {
                            "name": "echo",
                            "arguments": '{"value":"oi"}',
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "abc",
                "tool_name": "echo",
                "content": '{"echo":"oi"}',
            },
        ]
        native = provider._native_messages(messages)
        self.assertEqual(
            native[0]["tool_calls"][0]["function"]["arguments"],
            {"value": "oi"},
        )
        self.assertEqual(native[1], {"role": "tool", "content": '{"echo":"oi"}'})


if __name__ == "__main__":
    unittest.main()

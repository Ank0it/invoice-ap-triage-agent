"""LLM client wrapper with mock support for testing."""

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseLLMClient(ABC):
    @abstractmethod
    def invoke(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        pass


class MockLLMClient(BaseLLMClient):
    def __init__(self, responses: Optional[List[Dict[str, Any]]] = None):
        self.responses = responses or []
        self.call_count = 0
        self.last_messages: List[Dict[str, Any]] = []

    def set_responses(self, responses: List[Dict[str, Any]]):
        self.responses = responses
        self.call_count = 0

    def invoke(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        self.last_messages = messages
        if self.call_count >= len(self.responses):
            return {
                "role": "assistant",
                "content": '{"status": "NEEDS_REVIEW", "message": "No more mock responses configured."}',
                "tool_calls": None,
            }
        response = self.responses[self.call_count]
        self.call_count += 1
        return response


class OpenAIClient(BaseLLMClient):
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def invoke(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None,
        )
        msg = response.choices[0].message
        result = {
            "role": "assistant",
            "content": msg.content,
            "tool_calls": None,
        }
        if msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                }
                for tc in msg.tool_calls
            ]
        return result


def get_llm_client(mode: str = "deterministic") -> BaseLLMClient:
    if mode == "llm":
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            return OpenAIClient(api_key=api_key)
    return MockLLMClient()

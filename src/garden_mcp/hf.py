"""Hugging Face chat client (OpenAI-compatible router, tool calling).

The free Hugging Face Inference API exposes an OpenAI-style
/chat/completions endpoint at https://router.huggingface.co/v1 with tool
calling on supported instruction models. All this module needs is a token
(HF_TOKEN) - no paid plan.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from pydantic import BaseModel

ROUTER_BASE_URL = "https://router.huggingface.co/v1"
DEFAULT_MODEL = "meta-llama/Llama-3.3-70B-Instruct"


class HuggingFaceError(RuntimeError):
    pass


class ToolCallFunction(BaseModel):
    name: str
    arguments: str = ""  # JSON-encoded arguments, per the OpenAI format


class ToolCall(BaseModel):
    id: str
    function: ToolCallFunction


class ChatMessage(BaseModel):
    role: str
    content: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    tool_call_id: Optional[str] = None


class ChatChoice(BaseModel):
    message: ChatMessage


class ChatResponse(BaseModel):
    choices: list[ChatChoice]


class HuggingFaceChat:
    """Minimal chat-completions client with tool calling."""

    def __init__(self, token: Optional[str] = None, model: str = DEFAULT_MODEL,
                 base_url: str = ROUTER_BASE_URL,
                 transport: Optional[httpx.BaseTransport] = None,
                 timeout: float = 60.0):
        self.token = token or os.environ.get("HF_TOKEN")
        if not self.token:
            raise HuggingFaceError(
                "No Hugging Face token. Create a free one at "
                "https://huggingface.co/settings/tokens and set HF_TOKEN.")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def chat(self, messages: list[dict[str, Any]],
             tools: Optional[list[dict[str, Any]]] = None) -> ChatResponse:
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        with httpx.Client(transport=self._transport, timeout=self._timeout) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"})
        if resp.status_code != 200:
            raise HuggingFaceError(
                f"Hugging Face returned HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        if "error" in data:
            raise HuggingFaceError(f"Hugging Face error: {data['error']}")
        return ChatResponse(**data)

"""LLM-driven agent mode: a hosted model picks and chains the MCP tools.

Unlike agent.py, which chains the tools in a fixed order, this host hands the
server's tool schemas to a Hugging Face chat model and lets the model decide
which tools to call, in what order, from a natural-language question. Tool
results go back into the conversation until the model answers in plain text.

    export HF_TOKEN=hf_...
    python -m garden_mcp.llm_agent ask "why are my tomatoes dropping blossoms?"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .hf import DEFAULT_MODEL, HuggingFaceChat

MAX_ROUNDS = 8

SYSTEM_PROMPT = """You are a garden diagnostic assistant with MCP tools for a
planting log (SQLite) and weather (Open-Meteo). To answer a question about the
garden, look up the relevant plantings first, then pull weather or a diagnosis
for them. Chain as many tool calls as you need. When you have enough data,
answer plainly: what the data shows, the likely stress, and what to do about
it. Never invent plantings, dates, or weather numbers that the tools did not
return."""


def _tool_payload(result) -> str:
    """Serialize a CallToolResult to text for the conversation."""
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return json.dumps(structured, default=str)
    parts = [getattr(b, "text", "") for b in result.content]
    return "\n".join(p for p in parts if p)


class LLMGardenAgent:
    """Conversational tool-calling host over any connected MCP ClientSession."""

    def __init__(self, session: ClientSession, llm: HuggingFaceChat):
        self.session = session
        self.llm = llm

    @classmethod
    @asynccontextmanager
    async def connect(cls, db_path: Optional[str] = None, llm: Optional[HuggingFaceChat] = None):
        env = dict(os.environ)
        if db_path:
            env["GARDEN_DB_PATH"] = db_path
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "garden_mcp.server"], env=env
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield cls(session, llm or HuggingFaceChat())

    async def _openai_tools(self) -> list[dict[str, Any]]:
        tools = await self.session.list_tools()
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema,
                },
            }
            for t in tools.tools
        ]

    async def ask(self, question: str) -> str:
        """Run the conversational loop until the model answers in text."""
        tools = await self._openai_tools()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        for _ in range(MAX_ROUNDS):
            msg = self.llm.chat(messages, tools=tools).choices[0].message
            if not msg.tool_calls:
                return msg.content or ""
            messages.append(msg.model_dump(exclude_none=True))
            for call in msg.tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                    if not isinstance(args, dict):
                        args = {}
                except json.JSONDecodeError:
                    args = {}
                result = await self.session.call_tool(call.function.name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": _tool_payload(result),
                })
        raise RuntimeError(
            f"The model did not produce a final answer within {MAX_ROUNDS} rounds.")


async def _run(args) -> None:
    llm = HuggingFaceChat(model=args.model)
    async with LLMGardenAgent.connect(args.db, llm=llm) as agent:
        print(await agent.ask(args.question))


def main() -> None:
    parser = argparse.ArgumentParser(prog="garden-llm-agent")
    parser.add_argument("--db", default=None, help="Path to the planting-log SQLite file")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help="Hugging Face model with tool calling (default: %(default)s)")
    sub = parser.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="Ask a natural-language garden question")
    ask.add_argument("question")
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()

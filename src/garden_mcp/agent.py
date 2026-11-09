"""Agent host: connects to the MCP server and chains its tools.

The host speaks MCP over stdio exactly like any other MCP client. Its
garden-check loop is a multi-step chain: list plantings -> diagnose each one
(which itself chains log lookup -> weather fetch -> rules) -> aggregate a
single report.

    python -m garden_mcp.agent check --db garden.db
    python -m garden_mcp.agent tools
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

from .schemas import Diagnosis, GardenCheckReport, Planting


def _payload(result) -> Any:
    """Extract structured content from a CallToolResult, tolerating the
    {'result': ...} wrapper used when a tool has no declared output schema."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and set(structured) == {"result"}:
        return structured["result"]
    if structured is not None:
        return structured
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
    return None


class GardenAgent:
    """A minimal tool-calling host. Takes any connected MCP ClientSession,
    which keeps it testable in-memory and usable over stdio in production."""

    def __init__(self, session: ClientSession):
        self.session = session

    @classmethod
    @asynccontextmanager
    async def connect(cls, db_path: Optional[str] = None):
        env = dict(os.environ)
        if db_path:
            env["GARDEN_DB_PATH"] = db_path
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "garden_mcp.server"], env=env
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield cls(session)

    async def list_tool_names(self) -> list[str]:
        tools = await self.session.list_tools()
        return [t.name for t in tools.tools]

    async def call(self, tool: str, arguments: dict | None = None) -> Any:
        result = await self.session.call_tool(tool, arguments or {})
        if result.isError:
            text = " ".join(getattr(b, "text", "") for b in result.content)
            raise RuntimeError(f"tool {tool} failed: {text}")
        return _payload(result)

    async def garden_check(self, past_days: int = 7) -> GardenCheckReport:
        """Chain: list_plantings -> diagnose_planting (xN) -> aggregate."""
        plantings = [Planting(**p) for p in await self.call("list_plantings")]
        diagnoses: list[Diagnosis] = []
        for planting in plantings:
            raw = await self.call("diagnose_planting",
                                  {"planting_id": planting.id, "past_days": past_days})
            diagnoses.append(Diagnosis(**raw))
        flagged = sum(1 for d in diagnoses if d.flags)
        summary = (f"Checked {len(diagnoses)} planting(s): "
                   f"{flagged} with stress signals, {len(diagnoses) - flagged} clear.")
        return GardenCheckReport(checked_plantings=len(diagnoses),
                                 diagnoses=diagnoses, summary=summary)


async def _run(args) -> None:
    if args.command == "tools":
        async with GardenAgent.connect(args.db) as agent:
            for name in await agent.list_tool_names():
                print(name)
    elif args.command == "check":
        async with GardenAgent.connect(args.db) as agent:
            report = await agent.garden_check(past_days=args.past_days)
            print(report.model_dump_json(indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="garden-agent")
    parser.add_argument("--db", default=None, help="Path to the planting-log SQLite file")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("tools", help="List the tools the server exposes")
    check = sub.add_parser("check", help="Run a full garden check")
    check.add_argument("--past-days", type=int, default=7)
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()

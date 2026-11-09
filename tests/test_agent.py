import asyncio

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from conftest import make_client
from garden_mcp.agent import GardenAgent
from garden_mcp.schemas import StressKind
from garden_mcp.server import create_server


def run(coro):
    return asyncio.run(coro)


async def with_agent(server, fn):
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        await session.initialize()
        return await fn(GardenAgent(session))


def test_agent_lists_tools(tmp_path):
    server = create_server(db_path=str(tmp_path / "a.db"), weather_client=make_client())
    names = run(with_agent(server, lambda agent: agent.list_tool_names()))
    assert "diagnose_planting" in names


def test_garden_check_chains_tools(tmp_path):
    server = create_server(db_path=str(tmp_path / "b.db"),
                           weather_client=make_client(precip=0.0, et0=4.0))

    async def go(agent):
        await agent.call("log_planting", {
            "plant_name": "tomato", "latitude": 38.9, "longitude": -77.03,
            "planted_on": "2026-04-15"})
        await agent.call("log_planting", {
            "plant_name": "basil", "latitude": 38.9, "longitude": -77.03,
            "planted_on": "2026-05-01"})
        return await agent.garden_check()

    report = run(with_agent(server, go))
    assert report.checked_plantings == 2
    assert {d.plant_name for d in report.diagnoses} == {"tomato", "basil"}
    assert all(StressKind.DRY in {f.kind for f in d.flags} for d in report.diagnoses)
    assert "2 planting(s)" in report.summary


def test_garden_check_empty_garden(tmp_path):
    server = create_server(db_path=str(tmp_path / "c.db"), weather_client=make_client())
    report = run(with_agent(server, lambda agent: agent.garden_check()))
    assert report.checked_plantings == 0
    assert report.diagnoses == []


def test_agent_surfaces_tool_errors(tmp_path):
    server = create_server(db_path=str(tmp_path / "d.db"), weather_client=make_client())

    async def go(agent):
        with pytest.raises(RuntimeError, match="no planting"):
            await agent.call("diagnose_planting", {"planting_id": 7})

    run(with_agent(server, go))


def test_end_to_end_over_stdio(tmp_path):
    """The host spawns the real server subprocess and chains tools over stdio."""
    import os
    import sys
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    db_path = str(tmp_path / "stdio.db")
    env = dict(os.environ, GARDEN_DB_PATH=db_path)
    src = str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")

    async def go():
        params = StdioServerParameters(command=sys.executable,
                                       args=["-m", "garden_mcp.server"], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                agent = GardenAgent(session)
                await agent.call("log_planting", {
                    "plant_name": "kale", "latitude": 38.9, "longitude": -77.03,
                    "planted_on": "2026-03-20"})
                names = await agent.list_tool_names()
                assert "get_weather" in names
                # stdio server hits live Open-Meteo only in diagnose; skip network here
                listed = await agent.call("list_plantings")
                assert [p["plant_name"] for p in listed] == ["kale"]

    run(go())

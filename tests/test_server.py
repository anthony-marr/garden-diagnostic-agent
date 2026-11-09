import asyncio

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from conftest import make_client
from garden_mcp.server import create_server


def run(coro):
    return asyncio.run(coro)


async def call(server, tool, args=None):
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        await session.initialize()
        result = await session.call_tool(tool, args or {})
        from garden_mcp.agent import _payload
        return result, _payload(result)


@pytest.fixture
def server(tmp_path):
    return create_server(db_path=str(tmp_path / "srv.db"), weather_client=make_client())


def test_exposes_expected_tools(server):
    async def go():
        async with create_connected_server_and_client_session(server._mcp_server) as s:
            await s.initialize()
            return {t.name for t in (await s.list_tools()).tools}
    names = run(go())
    assert names == {"log_planting", "list_plantings", "log_observation",
                     "list_observations", "get_weather", "diagnose_planting"}


def test_log_and_list_plantings(server):
    _, created = run(call(server, "log_planting", {
        "plant_name": "tomato", "latitude": 38.9, "longitude": -77.03,
        "planted_on": "2026-04-15", "variety": "Roma"}))
    assert created["id"] == 1
    _, listed = run(call(server, "list_plantings"))
    assert [p["plant_name"] for p in listed] == ["tomato"]


def test_log_planting_rejects_bad_input(server):
    result, _ = run(call(server, "log_planting", {
        "plant_name": "tomato", "latitude": 38.9, "longitude": -77.03,
        "planted_on": "not a date"}))
    assert result.isError


def test_observations_flow(server):
    run(call(server, "log_planting", {
        "plant_name": "basil", "latitude": 38.9, "longitude": -77.03,
        "planted_on": "2026-05-01"}))
    _, obs = run(call(server, "log_observation", {
        "planting_id": 1, "note": "new growth", "observed_on": "2026-06-01"}))
    assert obs["planting_id"] == 1
    _, listed = run(call(server, "list_observations", {"planting_id": 1}))
    assert [o["note"] for o in listed] == ["new growth"]


def test_get_weather(tmp_path):
    server = create_server(db_path=str(tmp_path / "wx.db"),
                           weather_client=make_client(past_days=5, forecast_days=3))
    _, report = run(call(server, "get_weather", {
        "latitude": 38.9, "longitude": -77.03, "past_days": 5, "forecast_days": 3}))
    assert len(report["past"]) == 5
    assert len(report["forecast"]) == 3


def test_diagnose_planting_chains_log_and_weather(server, tmp_path):
    dry_server = create_server(db_path=str(tmp_path / "dry.db"),
                               weather_client=make_client(precip=0.0, et0=4.0))
    run(call(dry_server, "log_planting", {
        "plant_name": "pepper", "latitude": 38.9, "longitude": -77.03,
        "planted_on": "2026-04-20"}))
    _, diagnosis = run(call(dry_server, "diagnose_planting", {"planting_id": 1}))
    assert diagnosis["plant_name"] == "pepper"
    kinds = {f["kind"] for f in diagnosis["flags"]}
    assert "dry" in kinds
    assert diagnosis["recommendations"]


def test_diagnose_missing_planting_errors(server):
    result, _ = run(call(server, "diagnose_planting", {"planting_id": 99}))
    assert result.isError

import asyncio
import json

import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from conftest import make_client
from garden_mcp.hf import HuggingFaceChat
from garden_mcp.llm_agent import LLMGardenAgent, MAX_ROUNDS
from garden_mcp.server import create_server


def run(coro):
    return asyncio.run(coro)


def hf_response(content=None, tool_calls=None):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = [
            {"id": f"call_{i}", "type": "function",
             "function": {"name": name, "arguments": args}}
            for i, (name, args) in enumerate(tool_calls)
        ]
    return {"id": "chatcmpl-test", "object": "chat.completion",
            "created": 0, "model": "test-model",
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


def make_llm(script):
    """An HF client whose endpoint plays back a list of responses in order."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-token"
        calls.append(json.loads(request.content))
        body = script[min(len(calls) - 1, len(script) - 1)]
        return httpx.Response(200, content=json.dumps(body).encode())

    llm = HuggingFaceChat(token="test-token", model="test-model",
                          transport=httpx.MockTransport(handler))
    return llm, calls


async def with_llm_agent(server, llm, fn):
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        await session.initialize()
        return await fn(LLMGardenAgent(session, llm))


def test_llm_agent_chains_tools_from_question(tmp_path):
    server = create_server(db_path=str(tmp_path / "a.db"),
                           weather_client=make_client(precip=0.0, et0=4.0))
    llm, calls = make_llm([
        hf_response(tool_calls=[("list_plantings", "{}")]),
        hf_response(tool_calls=[("diagnose_planting", '{"planting_id": 1}')]),
        hf_response(content="Your Roma tomato is under high dry stress: almost no "
                            "rain against demand. Water more often."),
    ])

    async def go(agent):
        await agent.session.call_tool("log_planting", {
            "plant_name": "tomato", "variety": "Roma",
            "latitude": 38.9, "longitude": -77.03, "planted_on": "2026-04-15"})
        return await agent.ask("why are my tomatoes dropping blossoms?")

    answer = run(with_llm_agent(server, llm, go))
    assert "dry" in answer.lower()
    # three model calls: two tool rounds and the final answer
    assert len(calls) == 3
    # every call carried the tool schemas and full conversation so far
    assert calls[0]["tools"] and calls[0]["messages"][-1]["role"] == "user"
    assert calls[1]["messages"][-1]["role"] == "tool"
    names = [t["function"]["name"] for t in calls[0]["tools"]]
    assert "diagnose_planting" in names and "list_plantings" in names


def test_llm_agent_handles_bad_json_arguments(tmp_path):
    server = create_server(db_path=str(tmp_path / "b.db"), weather_client=make_client())
    llm, calls = make_llm([
        hf_response(tool_calls=[("list_plantings", "not json at all")]),
        hf_response(content="The log is empty, so there is nothing to diagnose yet."),
    ])
    answer = run(with_llm_agent(server, llm, lambda a: a.ask("what is in the log?")))
    assert "empty" in answer.lower()
    assert len(calls) == 2


def test_llm_agent_stops_at_max_rounds(tmp_path):
    server = create_server(db_path=str(tmp_path / "c.db"), weather_client=make_client())
    llm, calls = make_llm([
        hf_response(tool_calls=[("list_plantings", "{}")]),
    ] * MAX_ROUNDS)
    raised = None
    try:
        run(with_llm_agent(server, llm, lambda a: a.ask("loop forever")))
    except BaseException as exc:  # RuntimeError, possibly nested in ExceptionGroups
        raised = exc
    assert raised is not None
    leaves = []
    stack = [raised]
    while stack:
        exc = stack.pop()
        children = getattr(exc, "exceptions", None)
        if children:
            stack.extend(children)
        else:
            leaves.append(exc)
    assert any(isinstance(x, RuntimeError) and "final answer" in str(x) for x in leaves)
    assert len(calls) == MAX_ROUNDS


def test_hf_client_requires_token(monkeypatch):
    from garden_mcp.hf import HuggingFaceChat, HuggingFaceError
    monkeypatch.delenv("HF_TOKEN", raising=False)
    with pytest.raises(HuggingFaceError, match="HF_TOKEN"):
        HuggingFaceChat()


def test_hf_client_http_error(monkeypatch):
    from garden_mcp.hf import HuggingFaceChat, HuggingFaceError

    def handler(request):
        return httpx.Response(429, content=b'{"error": "rate limited"}')

    llm = HuggingFaceChat(token="test-token",
                          transport=httpx.MockTransport(handler))
    with pytest.raises(HuggingFaceError, match="429"):
        llm.chat([{"role": "user", "content": "hi"}])

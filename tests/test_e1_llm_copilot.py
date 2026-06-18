"""E1: Real LLM Copilot — tool-calling loop verified against a mock OpenAI server."""

from __future__ import annotations

import json

import httpx

from traffic_os.copilot import CopilotService
from traffic_os.intelligence import IntelligenceService
from traffic_os.knowledge_graph import KnowledgeGraphService
from traffic_os.planning import PlanningService
from traffic_os.simulation import SimulationEngine, build_grid_network, save_network
from traffic_os.storage import memory_storage


def _storage_with_traffic():
    net = build_grid_network(5)
    st = memory_storage()
    save_network(net, st.db)
    eng = SimulationEngine(net, st.settings)
    for _ in range(20):
        eng.persist_live(st, eng.step_once())
    return st


def test_health_modes():
    st = _storage_with_traffic()
    cp = CopilotService(st, IntelligenceService(st))
    assert cp.mode == "deterministic"
    assert "worst_junction" in cp.health()["tools"]

    st.settings.llm_api_key = "sk-test"
    assert cp.mode == "llm"
    assert cp.health()["model"]


def test_llm_tool_calling_loop(monkeypatch):
    st = _storage_with_traffic()
    st.settings.llm_api_key = "sk-test"
    intel = IntelligenceService(st)
    cp = CopilotService(
        st, intel, kg=KnowledgeGraphService(st, intel), planning=PlanningService(st)
    )

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls["n"] += 1
        if calls["n"] == 1:
            # first turn: model asks to call the worst_junction tool
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {"name": "worst_junction", "arguments": "{}"},
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
        # second turn: model has the tool result and answers
        assert any(m.get("role") == "tool" for m in body["messages"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "The worst junction is the central one; consider retiming its signal.",
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        cp,
        "_make_client",
        lambda: httpx.Client(transport=transport, base_url=st.settings.llm_base_url),
    )

    out = cp.ask("Which junction is worst and what should we do?")
    assert out["mode"] == "llm"
    assert "worst junction" in out["answer"].lower()
    assert out["tool"] == "worst_junction"
    assert calls["n"] == 2  # one tool round-trip + final answer


def test_llm_falls_back_to_deterministic_on_error(monkeypatch):
    st = _storage_with_traffic()
    st.settings.llm_api_key = "sk-test"
    cp = CopilotService(st, IntelligenceService(st))

    def boom():
        raise RuntimeError("LLM down")

    monkeypatch.setattr(cp, "_make_client", boom)
    out = cp.ask("Which junction is worst?")
    assert out["mode"] == "deterministic"
    assert out["tool"] == "worst_junction"

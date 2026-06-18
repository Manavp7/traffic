"""CopilotService — natural-language Q&A over Traffic-OS.

Uses an OpenAI-compatible LLM with function-calling when ``LLM_API_KEY`` is set,
otherwise a deterministic intent router that maps questions to the same typed tools.
The deterministic path guarantees the demo always works offline.
"""

from __future__ import annotations

from traffic_os.common.config import Settings
from traffic_os.common.logging import get_logger
from traffic_os.copilot.tools import CopilotTools, extract_junction, extract_period

log = get_logger("copilot")


class CopilotService:
    def __init__(
        self, storage, intelligence, *, kg=None, prediction=None, planning=None, recommendation=None
    ):
        self.storage = storage
        self.settings: Settings = getattr(storage, "settings", None) or Settings(mode="dev")
        self.tools = CopilotTools(
            storage,
            intelligence,
            kg=kg,
            prediction=prediction,
            planning=planning,
            recommendation=recommendation,
        )

    def ask(self, question: str) -> dict:
        if self.settings.llm_api_key:
            try:
                return self._ask_llm(question)
            except Exception as exc:  # pragma: no cover - network/LLM failure
                log.warning("LLM copilot failed (%s); using deterministic router", exc)
        return self._ask_deterministic(question)

    # -- deterministic intent router -------------------------------------- #
    def _ask_deterministic(self, question: str) -> dict:
        q = question.lower().strip()
        junction = extract_junction(question)

        def tagged(tool: str, result: dict) -> dict:
            return {
                "answer": result["answer"],
                "tool": tool,
                "data": result.get("data", {}),
                "mode": "deterministic",
            }

        # order matters: most specific intents first
        if "accident" in q and any(w in q for w in ("how many", "count", "number", "many")):
            return tagged("accidents_count", self.tools.accidents_count(extract_period(q)))
        if "risk" in q:
            return tagged("accident_risk", self.tools.accident_risk())
        if any(
            w in q
            for w in (
                "recommend",
                "what should",
                "what do we do",
                "action",
                "do about",
                "suggest",
                "fix",
            )
        ):
            return tagged("recommend_actions", self.tools.recommend_actions(junction))
        if any(
            w in q
            for w in (
                "cost",
                "economic",
                "loss",
                "fuel",
                "money",
                "lakh",
                "crore",
                "co2",
                "emission",
            )
        ):
            return tagged("economic_cost", self.tools.economic_cost())
        if any(
            w in q
            for w in ("forecast", "expected", "next hour", "predict", "will traffic", "later")
        ):
            return tagged("forecast", self.tools.forecast())
        if any(
            w in q
            for w in (
                "which junction",
                "worst",
                "maximum congestion",
                "max congestion",
                "bottleneck",
                "causes",
            )
        ):
            return tagged("worst_junction", self.tools.worst_junction())
        if "why" in q or ("bad" in q and "traffic" in q):
            return tagged("why_congested", self.tools.why_congested(junction))
        if any(w in q for w in ("hotspot", "top congestion", "congestion points")):
            return tagged("top_hotspots", self.tools.top_hotspots())
        if junction:
            return tagged("why_congested", self.tools.why_congested(junction))
        return tagged("network_summary", self.tools.network_summary())

    # -- LLM (function calling) ------------------------------------------- #
    def _tool_specs(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "why_congested",
                    "description": "Explain why a junction (or the worst one) is congested.",
                    "parameters": {
                        "type": "object",
                        "properties": {"junction": {"type": "string"}},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "worst_junction",
                    "description": "Identify the junction with maximum congestion and its bottleneck.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "top_hotspots",
                    "description": "List the top-N congestion points.",
                    "parameters": {"type": "object", "properties": {"n": {"type": "integer"}}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "accidents_count",
                    "description": "Count accidents over a period (today/week/month/year).",
                    "parameters": {"type": "object", "properties": {"period": {"type": "string"}}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "forecast",
                    "description": "Forecast network congestion N minutes ahead.",
                    "parameters": {
                        "type": "object",
                        "properties": {"horizon_min": {"type": "integer"}},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "accident_risk",
                    "description": "List roads with the highest predicted accident risk.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "economic_cost",
                    "description": "Estimate today's congestion economic cost (INR, fuel, CO2).",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "recommend_actions",
                    "description": "Recommend concrete actions to relieve congestion.",
                    "parameters": {
                        "type": "object",
                        "properties": {"junction": {"type": "string"}},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "network_summary",
                    "description": "Overall network status summary.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    def _call_tool(self, name: str, args: dict) -> dict:
        fn = getattr(self.tools, name, None)
        if fn is None:
            return {"answer": f"Unknown tool {name}", "data": {}}
        return fn(**(args or {}))

    def _ask_llm(self, question: str) -> dict:
        import json

        import httpx

        s = self.settings
        sys = (
            "You are the Traffic-OS Copilot for a city traffic command center. "
            "Use the provided tools to answer with real data. Be concise and specific."
        )
        messages = [{"role": "system", "content": sys}, {"role": "user", "content": question}]
        headers = {"Authorization": f"Bearer {s.llm_api_key}"}
        used_tool = None
        used_data: dict = {}
        with httpx.Client(base_url=s.llm_base_url, timeout=30) as client:
            for _ in range(4):
                resp = client.post(
                    "/chat/completions",
                    headers=headers,
                    json={
                        "model": s.llm_model,
                        "messages": messages,
                        "tools": self._tool_specs(),
                        "tool_choice": "auto",
                    },
                ).json()
                msg = resp["choices"][0]["message"]
                calls = msg.get("tool_calls")
                if not calls:
                    return {
                        "answer": msg.get("content", ""),
                        "tool": used_tool,
                        "data": used_data,
                        "mode": "llm",
                    }
                messages.append(msg)
                for call in calls:
                    name = call["function"]["name"]
                    args = json.loads(call["function"].get("arguments") or "{}")
                    result = self._call_tool(name, args)
                    used_tool, used_data = name, result.get("data", {})
                    messages.append(
                        {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)}
                    )
        return {
            "answer": "I could not complete the request.",
            "tool": used_tool,
            "data": used_data,
            "mode": "llm",
        }

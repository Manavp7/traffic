"""AI Copilot — KG-backed natural-language assistant (LLM + deterministic fallback)."""

from traffic_os.copilot.service import CopilotService
from traffic_os.copilot.tools import CopilotTools

__all__ = ["CopilotService", "CopilotTools"]

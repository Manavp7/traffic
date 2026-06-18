"""Decision Engine — adaptive signals, emergency corridors, disaster reroute."""

from traffic_os.decision.adaptive_signal import (
    SignalPlan,
    compute_signal_plan,
    plan_to_overrides,
)
from traffic_os.decision.disaster import Reroute, reroute_around
from traffic_os.decision.emergency import apply_corridor, plan_corridor
from traffic_os.decision.rl import JunctionEnv, RLResult, train_and_evaluate
from traffic_os.decision.routing import nearest_junction, route_segments
from traffic_os.decision.service import DecisionService

__all__ = [
    "DecisionService",
    "JunctionEnv",
    "RLResult",
    "train_and_evaluate",
    "SignalPlan",
    "compute_signal_plan",
    "plan_to_overrides",
    "plan_corridor",
    "apply_corridor",
    "reroute_around",
    "Reroute",
    "nearest_junction",
    "route_segments",
]

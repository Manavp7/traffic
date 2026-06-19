"""Decision Engine — adaptive signals, emergency corridors, disaster reroute."""

from traffic_os.decision.adaptive_signal import (
    SignalPlan,
    compute_signal_plan,
    plan_to_overrides,
)
from traffic_os.decision.convoy import plan_convoy
from traffic_os.decision.disaster import Reroute, reroute_around
from traffic_os.decision.dispatch import DispatchService, Unit, default_depots
from traffic_os.decision.emergency import apply_corridor, plan_corridor
from traffic_os.decision.evacuation import nearest_exits, plan_evacuation
from traffic_os.decision.rl import JunctionEnv, RLResult, train_and_evaluate
from traffic_os.decision.routing import nearest_junction, route_segments
from traffic_os.decision.service import DecisionService

__all__ = [
    "DecisionService",
    "JunctionEnv",
    "RLResult",
    "train_and_evaluate",
    "plan_convoy",
    "DispatchService",
    "Unit",
    "default_depots",
    "plan_evacuation",
    "nearest_exits",
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

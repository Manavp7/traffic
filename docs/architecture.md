# Traffic-OS Architecture

**National Traffic Intelligence Operating System — Detect · Predict · Recommend · Simulate · Optimize**

## Layered pipeline

```
Data Sources (sim / CV / citizen / weather / events)
  → Perception            (YOLO11 + ByteTrack)                    traffic_os/perception
  → Traffic Intelligence  (congestion, hotspots, bottleneck,      traffic_os/intelligence
                           tracking-based collision detection)
  → Knowledge Graph       (Neo4j / Kùzu — causal reasoning)       traffic_os/knowledge_graph
  → Prediction            (forecast + accident-risk)              traffic_os/prediction
  → Decision Engine       (adaptive signals + emergency corridor) traffic_os/decision
  → Strategic Planning    (digital twin + infra what-if +         traffic_os/planning
                           economic loss)
  → Recommendation Engine (concrete ranked actions)               traffic_os/recommendation
  → Control Layer         (signal preemption / reroute)           traffic_os/decision
  → Command Center        (Police + Commissioner dashboards)      dashboard/
        ↑ Edge AI nodes feed Perception (traffic_os/edge)
```

## Design principles

- **Ports & adapters** (`traffic_os/storage`): one codebase, two runtimes.
  - **dev**: SQLite (+ Shapely geometry), embedded **Kùzu** graph DB, filesystem blobs,
    in-process async event bus — *no Docker, no GPU*.
  - **prod**: PostgreSQL/PostGIS, TimescaleDB, **Neo4j**, Redis, MinIO, Redpanda
    (`infra/docker-compose.yml`). Selected via `TOS_MODE`.
- **Simulation-first digital twin** (`traffic_os/simulation`): a mesoscopic microsimulator over a
  real (OSM) or synthetic grid network generates live + historical data in lieu of physical
  sensors, and powers the what-if simulator. A subset of vehicles are "probes" whose full
  trajectories drive the violation + collision layers (parity with real GPS/CV).
- **Explainable over flashy**: rule-based adaptive signals (max-pressure) and tracking-based
  collision detection — no opaque video models or hard-to-demo RL in the MVP (see roadmap).
- **Knowledge-graph causality**: every domain entity (roads, signals, incidents, weather,
  events) is linked so the Copilot can answer *why* (`why_congested(junction)`).

## Data model

Shared Pydantic schemas in `traffic_os/schemas` form the contract across all layers:
`Junction`, `RoadSegment`, `Signal*`, `Track`/`Detection`, `SegmentMetric`, `Incident`,
`CollisionEvent`, `Violation`, `Forecast`, `AccidentRisk`, `EconomicImpact`, `InfraScenario`/
`ScenarioResult`, `Recommendation`, `GreenCorridor`, `CityEvent`, `Weather`, `CitizenReport`,
plus knowledge-graph `KGNode`/`KGEdge`/`CausalFactor`.

## Live data flow

The API (`traffic_os/api`) runs the simulation loop, overwriting a bounded `live_metric`
collection each tick (no unbounded growth) and publishing compact snapshots to the event bus
(WebSocket `/ws`). Heavy analytics (forecast, accident-risk, recommendations) are trained once
and refreshed by a background thread into an in-memory cache for snappy dashboards.

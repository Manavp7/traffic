# Traffic-OS — National Traffic Intelligence Operating System

**Detect · Predict · Recommend · Simulate · Optimize**

A decision-support operating system for city/national traffic authorities. Not "traffic
detection" and not "a dashboard" — an end-to-end platform spanning perception, intelligence,
causal reasoning, prediction, decision-making, strategic city planning, and command-center
visualisation.

## Architecture (layers)

```
Data Sources (sim / CV / citizen / weather / events)
  → Perception            (YOLO11 + ByteTrack)
  → Traffic Intelligence  (congestion, hotspots, bottleneck, collision detection)
  → Knowledge Graph       (Neo4j / Kùzu — causal reasoning)
  → Prediction            (forecast + accident-risk)
  → Decision Engine       (adaptive signals + emergency green corridors)
  → Strategic Planning    (digital twin + infra what-if + economic loss)
  → Recommendation Engine (concrete actions, not status)
  → Control Layer
  → Command Center        (Police + Commissioner dashboards)     [Edge AI nodes feed Perception]
```

## Design principles

- **Ports & adapters**: identical code runs in a zero-dependency **dev mode**
  (SQLite + Shapely, embedded **Kùzu** graph DB, filesystem blobs, in-process event bus) and a
  **prod mode** (PostgreSQL/PostGIS, TimescaleDB, **Neo4j**, Redis, MinIO, Redpanda via
  `infra/docker-compose.yml`). No Docker or GPU required for the demo.
- **Simulation-first**: a digital twin over a real (or synthetic) road network generates live
  + historical data in lieu of real sensor feeds, while a real YOLO+ByteTrack pipeline proves
  the perception layer on sample video.
- **Explainable over flashy**: rule-based adaptive signals and tracking-based collision
  detection (no opaque video models or hard-to-demo RL in the MVP — those are on the roadmap).

## Quickstart (dev, no Docker/GPU)

```bash
make install          # base + dev deps into .venv (uses uv)
make install-ml       # optional: ML + CV + GIS extras (YOLO, XGBoost, osmnx)
make test             # run the test suite
.venv/bin/python -m traffic_os.cli info
```

## Repository layout

```
traffic_os/
  common/         config, logging, geo/time utils, economic factors
  schemas/        shared Pydantic domain models + enums + KG types
  storage/        ports + dev/prod adapters (db, blob, cache, eventbus, graph)
  simulation/     digital twin / synthetic traffic + history
  perception/     YOLO + ByteTrack pipeline
  intelligence/   congestion, hotspots, bottleneck, collision detection
  knowledge_graph/ causal reasoning over the graph
  violations/     rule-based violation detectors
  prediction/     forecasting + accident-risk
  decision/       adaptive signals + emergency corridors + disaster reroute
  planning/       infra what-if simulator + economic loss engine
  recommendation/ AI recommendation engine
  copilot/        KG-backed assistant (LLM + deterministic fallback)
  edge/           Edge AI node stub
  api/            FastAPI gateway + WebSocket
dashboard/        React + MapLibre (Command Center + Commissioner)
infra/            docker-compose + migrations
docs/             architecture, runbook, roadmap, edge-ai, api
```

See `docs/` for architecture details and the roadmap mapping every remaining vision module to a
concrete future task.

## License

MIT

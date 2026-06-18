# API Reference

FastAPI gateway (`traffic_os/api/app.py`). Interactive docs at `/docs` (OpenAPI at `/openapi.json`).

| Method | Path | Description |
|---|---|---|
| GET | `/healthz` | Liveness + sim tick + segment count |
| GET | `/network` | Junctions, road segments (with geometry), signals |
| GET | `/live` | Latest live snapshot (vehicles, congestion, incidents) |
| WS  | `/ws` | Live tick stream (push) |
| GET | `/intelligence/summary` | Network avg congestion, severe count, worst junction |
| GET | `/intelligence/hotspots?n=` | Top-N congestion points |
| GET | `/intelligence/bottlenecks?n=` | Root-cause bottlenecks |
| GET | `/intelligence/travel-time?origin=&destination=` | Current vs free-flow travel time |
| GET | `/collisions` | Tracking-based collision/sudden-stop/abnormal-motion events |
| GET | `/violations` | Run detectors + recent violations + counts |
| GET | `/incidents` | Active/recent incidents |
| GET | `/forecast?horizon=&segment=` | Congestion forecast (per segment or all) |
| GET | `/risk?n=` | Highest accident-risk roads + backtests |
| GET | `/signals` | Signal states + adaptive recommended plan |
| GET | `/signals/evaluate` | Fixed vs adaptive throughput comparison |
| POST | `/emergency` | Plan an emergency green corridor |
| POST | `/disaster/reroute` | Reroute around blocked segments |
| GET | `/economics` | Economic loss summary (₹/day) + per-segment breakdown |
| POST | `/planning/scenario` | Run an infrastructure what-if simulation |
| GET | `/recommendations?n=` | Ranked AI action recommendations |
| GET | `/kg/why?junction=` | Causal explanation for a junction |
| GET | `/kg/stats` | Knowledge-graph node/edge counts |
| POST | `/copilot` | Natural-language Q&A (`{"question": "..."}`) |
| GET | `/commissioner` | Aggregate KPIs for decision-makers |
| GET/POST | `/reports` | Citizen reports (list / create) |
| POST | `/ingest/camera` | Edge-node metric uplink |
| GET | `/cameras` | Recent camera metrics |
| GET | `/events` | City events |

Auth: optional API key via `TOS_API_KEY`. LLM Copilot via `TOS_LLM_API_KEY` (else deterministic).

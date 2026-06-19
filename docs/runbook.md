# Runbook

## Prerequisites
- Python 3.11+ and Node 18+. No Docker or GPU required for dev mode.
- [`uv`](https://github.com/astral-sh/uv) recommended (`pip install uv`).

## Install
```bash
make install        # base + dev deps into .venv
make install-ml     # optional: ML + CV + GIS extras (YOLO, XGBoost, osmnx)
```

## Fetch sample media (for the perception/edge demos)
```bash
bash scripts/fetch_samples.sh   # downloads sample traffic videos + YOLO11n weights
```

## One-command demo
```bash
make demo           # seed network + history, start API (:8000) and dashboard (:5173)
```
Open http://localhost:5173 — **Command Center** (live map, hotspots, bottlenecks,
recommendations, Copilot) and **Commissioner** (economic loss, accident risk, forecast,
infrastructure what-if simulator).

## Individual commands
```bash
.venv/bin/python -m traffic_os.cli seed                 # build + persist the road network
.venv/bin/python -m traffic_os.cli history --days 14    # generate historical metrics
.venv/bin/python -m traffic_os.cli simulate --ticks 200 # run the live microsim
.venv/bin/python -m traffic_os.cli train                # train forecast + accident-risk
.venv/bin/python -m traffic_os.cli perceive --video data/samples/highway.mp4   # YOLO+ByteTrack
.venv/bin/python -m traffic_os.cli edge --video data/samples/highway.mp4       # edge node uplink
make serve                                              # API only
```

## Tests & quality gate
```bash
.venv/bin/ruff check traffic_os tests
.venv/bin/black --check traffic_os tests
.venv/bin/mypy traffic_os
.venv/bin/pytest -q
cd dashboard && npm test && npm run build
```

## Production mode
```bash
docker compose -f infra/docker-compose.yml up -d   # Postgres/PostGIS, Timescale, Neo4j, Redis, MinIO, Redpanda
TOS_MODE=prod .venv/bin/uvicorn traffic_os.api.app:app --host 0.0.0.0 --port 8000
```
Configure via `TOS_*` env vars (see `traffic_os/common/config.py`), e.g. `TOS_LLM_API_KEY` to
enable the LLM-backed Copilot (otherwise the deterministic router is used), `TOS_SIM_USE_OSM=true`
+ `TOS_SIM_PLACE="Indiranagar, Bengaluru, India"` to build a real OSM network.

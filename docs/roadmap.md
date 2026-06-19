# Roadmap

The MVP exercises the full pipeline end-to-end. The expansion (E1–E18) then built out most
of the original backlog. This page tracks what is **delivered** vs what remains future work.

## Delivered in the expansion (E1–E18)
- **Real LLM Copilot** (function-calling) with deterministic fallback + `/copilot/health`.
- **Real OSM city** networks via osmnx with graphml caching (`seed --osm`).
- **Live adaptive signal apply** + auto mode (dashboard "Apply adaptive plan").
- **Emergency green corridor on the map** (click-to-route + ETA savings).
- **Operational alerts** feed (`/alerts`) + dashboard.
- **Commissioner CSV / PDF export**.
- **Vision violations**: real **triple-riding** detection (COCO) + framework for others.
- **Road-health** pothole detection (CV heuristic + pluggable ML).
- **Citizen PWA** (report / live / route) with manifest + service worker.
- **Historical analytics** (timeseries + diurnal/daily profiles).
- **Auth + RBAC** (API key, operator/commissioner roles, audit log).
- **Production adapters**: Neo4j, Redis, MinIO, Kafka (+ skip-guarded integration tests).
- **Multi-camera** registry + edge ingestion.
- **RL signal control** (optional single-junction DQN) — alongside max-pressure.
- **3D digital twin** (Three.js) — congestion-coloured network + live vehicles.
- **Public-transport + freight** modules.
- **Multi-city / national** rollup.
- **Optional VideoMAE** accident classifier with tracking-based fallback.

## Delivered in expansion 2 (F1–J6)
- **Enforcement**: ANPR + e-Challan with tamper-evident evidence locker (SHA-256 + chain-of-custody),
  stolen/blacklist watchlist, enforcement zones + auto-evidence, VRU near-miss, driver-behavior scoring.
- **Sustainability**: AQI + health impact, dynamic congestion pricing (revenue + diversion),
  EV charging demand + grid load, carbon / net-zero tracking.
- **Mobility**: smart parking, multimodal trip planner, incident auto-dispatch, disaster evacuation,
  VIP/convoy rolling green-wave.
- **Decision intelligence**: scenario library + ROI/payback, signal A/B testing (Welch t-test),
  anomaly detection (z-score), KPI/SLA + history replay, voice + multilingual (EN/HI) Copilot.
- **Platform**: data-connector providers (+ third-party stubs), citizen notifications + geofence,
  Prometheus `/metrics` + rate limiting, JWT auth over RBAC, open-data GeoJSON portal,
  simulation calibration + edge store-and-forward.

## Still future work (needs hardware / data / GPU / scale)
- RTSP/CCTV at city scale with hardware-accelerated decode (DeepStream/TensorRT); drones; real GPS/AVL.
- Helmet / seatbelt / mobile-phone **trained** classifiers (framework + interface are in place).
- Accident-specific **fine-tuned** video models (VideoMAE wired; needs labelled crash data + GPU).
- Multi-agent / city-scale **RL** signal control (single-junction DQN demonstrated).
- CesiumJS terrain-grade 3D (Three.js twin delivered).
- Production Kafka/Redpanda streaming at scale; multi-tenant SaaS hardening; SSO.
- SUMO co-simulation for higher-fidelity microsimulation.
- Real accident-labelled datasets to replace the documented latent-hazard training labels.

# Roadmap

The MVP exercises the full pipeline end-to-end. The items below are deliberately **out of scope**
for the MVP (they need real hardware, labelled data, or large training budgets) but the
architecture is designed so each plugs into an existing interface.

## Perception / ingestion
- **RTSP/CCTV live ingestion** (GStreamer/DeepStream) + **drone** + real **GPS/AVL** feeds.
- **RT-DETR / YOLOv12** detector upgrade (swap behind `YOLODetector`).
- Vision-model violations behind `VisionViolationDetector`: **no-helmet, no-seatbelt, mobile-phone
  use, triple-riding, zebra-crossing**.
- **Road-health**: pothole / crack / waterlogging segmentation.
- Per-camera **homography calibration** (pixel → lat/lon) to fuse camera tracks into the geo graph.

## Models
- **Video action recognition** (VideoMAE / MMAction2) for richer crash classification — the MVP
  uses explainable tracking-based collision/sudden-stop/abnormal-motion detection instead.
- **Reinforcement-learning** signal control (DQN/PPO, multi-agent) — the MVP ships an explainable
  max-pressure adaptive engine; RL is a research extension, harder to validate for review panels.
- Real accident-labelled datasets to replace the documented latent-hazard training labels.

## Products (each its own workstream)
- **Public-transport intelligence** (bus delays, route efficiency, passenger density).
- **Freight optimisation** (truck routing, fuel-cost reduction).
- **Citizen mobile app** (the API already exposes `/reports`, `/live`, routing).

## Platform / scale
- Production **Kafka/Redpanda** streaming at city scale (interface: `EventBus`).
- **CesiumJS / Three.js** 3D digital twin (MVP ships a 2D MapLibre twin).
- **SUMO** co-simulation for higher-fidelity microsimulation.
- **Auth/RBAC**, multi-tenant government deployment, audit logging.
- Physical **Edge AI** hardware rollout (see `edge-ai.md`).

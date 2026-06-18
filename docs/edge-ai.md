# Edge AI Architecture

```
Camera (RTSP)  →  Edge AI Node (on-device YOLO+ByteTrack)  →  Command Center (uplink metrics)
```

Instead of streaming raw video to the cloud, detection runs **on the edge device** and only
compact metrics (per-frame counts, occupancy %, queue length, unique track count) are uplinked.
This slashes bandwidth, reduces cloud GPU cost, and preserves privacy (no raw faces/plates leave
the device).

## Demonstrated
`traffic_os/edge/node.py` (`EdgeNode`) runs real YOLO11+ByteTrack locally and emits
`CameraFrameMetric` objects to a sink (an HTTP uplink to `POST /ingest/camera`, or any callback).

```bash
.venv/bin/python -m traffic_os.cli edge --video data/samples/highway.mp4 --api http://localhost:8000
```
Typical result: ~5 KB of metrics uplinked vs hundreds of MB of raw frames — a >99% bandwidth
reduction — while the Command Center still sees live counts/occupancy/queue per camera.

## Target hardware (deployment-ready)

| Device | YOLO model | ~Throughput | Notes |
|---|---|---|---|
| **NVIDIA Jetson Orin Nano** | YOLO11n/s (TensorRT) | 30–60 FPS | Best perf/W; multi-stream with DeepStream |
| **Raspberry Pi 5 (+ Hailo-8L)** | YOLO11n | 15–30 FPS | Low cost; Hailo NPU accelerator |
| **Intel NUC (+ OpenVINO)** | YOLO11n/s | 25–45 FPS | x86; easy ops; iGPU/VPU offload |

## Production path (roadmap)
- RTSP ingest (GStreamer/DeepStream), hardware-accelerated decode + TensorRT/OpenVINO inference.
- Store-and-forward uplink (MQTT/Kafka) with offline buffering on the edge.
- OTA model updates and per-camera homography calibration (pixel → metres / lat-lon).
- On-device privacy: blur faces/plates before any optional snapshot upload.

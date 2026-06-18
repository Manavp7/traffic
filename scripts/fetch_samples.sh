#!/usr/bin/env bash
# Fetch sample media + model weights for the perception demo (not committed to git).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/samples models

echo "Downloading sample traffic videos ..."
curl -fsSL -o data/samples/highway.mp4 \
  "https://github.com/AarohiSingla/Speed-detection-of-vehicles/raw/main/highway_mini.mp4" || \
  echo "WARN: highway.mp4 download failed"
curl -fsSL -o data/samples/traffic.mp4 \
  "https://github.com/intel-iot-devkit/sample-videos/raw/master/person-bicycle-car-detection.mp4" || \
  echo "WARN: traffic.mp4 download failed"

echo "Downloading YOLO11n weights ..."
curl -fsSL -o models/yolo11n.pt \
  "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11n.pt" || \
  echo "WARN: yolo11n.pt download failed (ultralytics will auto-download on first run)"

echo "Done. Samples in data/samples, weights in models/."

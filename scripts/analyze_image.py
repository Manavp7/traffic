"""Run the Traffic-OS perception + intelligence stack on a single image.

Usage:
    .venv/bin/python scripts/analyze_image.py <image_path>

Outputs: per-class vehicle counts, road occupancy %, queue estimate, and a
congestion verdict — the same pipeline the live system uses, on one still image.
"""

from __future__ import annotations

import json
import sys

from traffic_os.perception.detector import YOLODetector
from traffic_os.perception.metrics import counts_by_class, occupancy_pct


def analyze(path: str) -> dict:
    import cv2

    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(path)
    h, w = img.shape[:2]
    frame_area = float(h * w)

    det = YOLODetector(conf=0.25)  # lower conf: dense, partly-occluded vehicles
    dets = det.detect(img)

    counts = counts_by_class(dets)
    vehicles = [d for d in dets if d.cls.value != "pedestrian"]
    occ = occupancy_pct(dets, frame_area, roi_frac=0.9)  # near-full-frame is roadway

    # congestion verdict from occupancy + vehicle density (no speed in a still image)
    veh_density = len(vehicles) / (frame_area / 1e6)  # vehicles per megapixel
    score = min(100.0, occ * 0.8 + min(len(vehicles), 100) * 0.6)
    level = ("severe" if score >= 75 else "heavy" if score >= 50
             else "moderate" if score >= 25 else "free")

    # annotate + save
    out_path = path.rsplit(".", 1)[0] + "_annotated.jpg"
    annotated = img.copy()
    colors = {"car": (0, 200, 0), "bus": (255, 140, 0), "truck": (0, 0, 255),
              "bike": (255, 0, 255), "auto": (0, 200, 200), "pedestrian": (200, 200, 200)}
    for d in dets:
        x1, y1, x2, y2 = (int(v) for v in d.bbox)
        c = colors.get(d.cls.value, (255, 255, 255))
        cv2.rectangle(annotated, (x1, y1), (x2, y2), c, 2)
    cv2.imwrite(out_path, annotated)

    return {
        "image": path,
        "resolution": f"{w}x{h}",
        "total_objects": len(dets),
        "total_vehicles": len(vehicles),
        "counts_by_class": counts,
        "road_occupancy_pct": occ,
        "vehicles_per_megapixel": round(veh_density, 1),
        "congestion_score": round(score, 1),
        "congestion_level": level,
        "annotated_image": out_path,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: analyze_image.py <image_path>")
        raise SystemExit(2)
    print(json.dumps(analyze(sys.argv[1]), indent=2))

"""E8: road-health (pothole) detection — CV heuristic on a synthetic image."""

from __future__ import annotations

import pytest

pytest.importorskip("cv2")
pytest.importorskip("numpy")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from traffic_os.perception import detect_potholes_cv  # noqa: E402
from traffic_os.perception.road_health import RoadHealthModel  # noqa: E402


def _road_with_pothole():
    img = np.full((400, 600, 3), 170, dtype=np.uint8)  # light grey road
    img += np.random.randint(-8, 8, img.shape, dtype="int16").astype("uint8")
    # a dark, round pothole
    cv2.ellipse(img, (300, 200), (45, 38), 0, 0, 360, (35, 35, 35), -1)
    return img


def test_detect_pothole_on_synthetic_image():
    issues = detect_potholes_cv(_road_with_pothole(), source_id="cam-test")
    assert issues, "expected at least one pothole candidate"
    assert all(i.kind.value == "pothole" for i in issues)
    # a detected box should sit near the painted pothole centre (300,200)
    near = [
        i for i in issues if i.bbox and i.bbox[0] < 300 < i.bbox[2] and i.bbox[1] < 200 < i.bbox[3]
    ]
    assert near


def test_clean_road_few_or_no_potholes():
    clean = np.full((400, 600, 3), 175, dtype=np.uint8)
    issues = detect_potholes_cv(clean, source_id="cam-test")
    assert len(issues) == 0


def test_model_falls_back_to_heuristic():
    m = RoadHealthModel(model_path=None)
    assert m.method == "cv-heuristic"
    assert isinstance(m.analyze(_road_with_pothole()), list)

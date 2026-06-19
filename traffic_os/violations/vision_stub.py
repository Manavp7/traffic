"""Interface stubs for vision-model violations (roadmap).

Helmet, seatbelt, mobile-phone use, triple-riding and zebra-crossing violations
require dedicated classification models on cropped vehicle/rider images. The
interface is defined here so they slot into the same pipeline when models land.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from traffic_os.schemas import Violation


class VisionViolationDetector(ABC):
    """Detect violations from an image crop of a tracked rider/vehicle."""

    violation_types: list[str] = []

    @abstractmethod
    def detect(self, image, track_id: str, lat: float, lon: float) -> list[Violation]:
        """Return violations found in ``image`` (roadmap: implement per model)."""
        raise NotImplementedError

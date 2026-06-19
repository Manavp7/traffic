"""ANPR (Automatic Number-Plate Recognition).

- ``SyntheticANPR``: deterministic plate per track id (used with the simulator so the
  full e-Challan flow is demonstrable end-to-end without real plate imagery).
- ``OcrANPR``: pluggable real recogniser (EasyOCR) over a cropped plate image — used
  when running on real camera frames. Optional dependency.
"""

from __future__ import annotations

import hashlib

_STATE_CODES = ["KA", "MH", "DL", "TN", "AP", "GJ", "UP", "RJ", "WB", "KL"]
_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def plate_for_track(track_id: str | None) -> str:
    """Deterministic, realistic Indian plate string for a given track id."""
    seed = track_id or "unknown"
    h = hashlib.sha256(seed.encode()).hexdigest()
    n = int(h, 16)
    state = _STATE_CODES[n % len(_STATE_CODES)]
    rto = (n >> 8) % 100
    l1 = _LETTERS[(n >> 16) % len(_LETTERS)]
    l2 = _LETTERS[(n >> 24) % len(_LETTERS)]
    num = (n >> 32) % 10000
    return f"{state}{rto:02d}{l1}{l2}{num:04d}"


class SyntheticANPR:
    def recognize_track(self, track_id: str | None) -> str:
        return plate_for_track(track_id)


class OcrANPR:  # pragma: no cover - requires easyocr + real plate crops
    def __init__(self, langs=("en",)) -> None:
        import easyocr

        self.reader = easyocr.Reader(list(langs))

    def recognize_image(self, image) -> str | None:
        results = self.reader.readtext(image, detail=0)
        for text in results:
            cleaned = "".join(c for c in text.upper() if c.isalnum())
            if 6 <= len(cleaned) <= 12:
                return cleaned
        return None

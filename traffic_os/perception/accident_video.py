"""Optional video-based accident recognition (VideoMAE).

This is an *optional* enhancement. A pluggable :class:`VideoAccidentClassifier` runs a
real VideoMAE video-classification model when ``transformers`` + weights are available.
Since accident-specific fine-tuned weights are not bundled (and need a GPU to train),
the **tracking-based** collision/sudden-stop detector remains the primary, always-on
signal — and is used here as the fallback so the pipeline is fully functional offline.
"""

from __future__ import annotations

from typing import Any

from traffic_os.common.logging import get_logger
from traffic_os.intelligence.collision import detect_all
from traffic_os.schemas import Track

log = get_logger("perception.accident_video")


class VideoAccidentClassifier:
    """Wraps a transformers VideoMAE video classifier (optional dependency)."""

    def __init__(self, model_name: str = "MCG-NJU/videomae-base-finetuned-kinetics") -> None:
        from transformers import VideoMAEForVideoClassification, VideoMAEImageProcessor

        self.processor = VideoMAEImageProcessor.from_pretrained(model_name)
        self.model = VideoMAEForVideoClassification.from_pretrained(model_name)
        self.model.eval()

    def classify(self, frames: list) -> dict[str, Any]:
        import torch

        inputs = self.processor(frames, return_tensors="pt")
        with torch.no_grad():
            logits = self.model(**inputs).logits
        idx = int(logits.argmax(-1).item())
        label = self.model.config.id2label.get(idx, str(idx))
        score = float(torch.softmax(logits, -1).max().item())
        return {"label": label, "score": round(score, 3)}


def analyze_clip(
    *,
    frames: list | None = None,
    tracks: list[Track] | None = None,
    net=None,
    model: VideoAccidentClassifier | None = None,
) -> dict[str, Any]:
    """Analyse an incident clip.

    - If a VideoMAE ``model`` + ``frames`` are supplied → run the video classifier.
    - Otherwise fall back to the tracking-based collision detector over ``tracks``.
    """
    if model is not None and frames:
        result = model.classify(frames)
        return {"method": "videomae", **result}
    events = detect_all(tracks or [], net)
    return {
        "method": "tracking-based",
        "events": [e.model_dump(mode="json") for e in events],
        "count": len(events),
    }

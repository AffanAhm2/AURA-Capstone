from __future__ import annotations

import os
import time
from typing import Any

from . import config
from .models import Detection, SensorStatus
from .queue_utils import put_latest


def _priority_for_label(label: str) -> int:
    name = label.lower().strip()
    if any(name in v or v in name for v in config.PRIORITY_MAP["critical"]):
        return 4
    if any(name in v or v in name for v in config.PRIORITY_MAP["high"]):
        return 3
    if any(name in v or v in name for v in config.PRIORITY_MAP["medium"]):
        return 2
    if any(name in v or v in name for v in config.PRIORITY_MAP["low"]):
        return 1
    return 2


def _direction_from_center(x_center: float, width: float) -> str:
    if width <= 0:
        return "12 o'clock"
    ratio = x_center / width
    if ratio < 0.25:
        return "10 o'clock"
    if ratio < 0.40:
        return "11 o'clock"
    if ratio < 0.60:
        return "12 o'clock"
    if ratio < 0.75:
        return "1 o'clock"
    return "2 o'clock"


def vision_process_worker(
    vision_in_q: Any,
    vision_out_q: Any,
    status_q: Any,
    stop_event: Any,
) -> None:
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")

    model = None
    target_classes = [n.lower() for n in config.VISION_TARGET_CLASSES]
    try:
        from ultralytics import YOLO  # type: ignore

        model = YOLO(config.VISION_MODEL_PATH)
        if target_classes and hasattr(model, "set_classes"):
            model.set_classes(target_classes)
        put_latest(
            status_q,
            SensorStatus("vision", True, f"Vision model loaded: {config.VISION_MODEL_PATH}", time.time()),
        )
    except Exception as exc:
        put_latest(status_q, SensorStatus("vision", False, f"Vision offline: {exc}", time.time()))

    while not stop_event.is_set():
        try:
            frame = vision_in_q.get(timeout=0.2)
        except Exception:
            continue

        if model is None:
            put_latest(vision_out_q, [])
            continue

        detections: list[Detection] = []
        try:
            results = model(frame, imgsz=config.VISION_IMGSZ, conf=config.VISION_CONFIDENCE, verbose=False)
            width = frame.shape[1]
            if results:
                r = results[0]
                boxes = getattr(r, "boxes", None)
                names = getattr(r, "names", {})
                if boxes is not None and getattr(boxes, "xyxy", None) is not None:
                    for i in range(len(boxes.xyxy)):
                        cls_id = int(boxes.cls[i].item())
                        conf = float(boxes.conf[i].item())
                        x1, y1, x2, y2 = [int(v) for v in boxes.xyxy[i].tolist()]
                        label = str(names.get(cls_id, f"class_{cls_id}")).lower()
                        if target_classes and label not in target_classes:
                            continue
                        x_center = (x1 + x2) / 2.0
                        center_bias = abs((x_center / max(width, 1)) - 0.5)
                        detections.append(
                            Detection(
                                label=label,
                                confidence=conf,
                                bbox=(x1, y1, x2, y2),
                                center_bias=center_bias,
                                priority_score=_priority_for_label(label),
                                direction=_direction_from_center(x_center, width),
                            )
                        )
        except Exception as exc:
            put_latest(status_q, SensorStatus("vision", False, f"Vision inference error: {exc}", time.time()))
            detections = []

        put_latest(vision_out_q, detections)

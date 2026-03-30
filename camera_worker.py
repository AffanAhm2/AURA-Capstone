from __future__ import annotations

import threading
import time
from typing import Any

from . import config
from .models import SensorStatus
from .queue_utils import put_latest


def camera_thread_worker(frame_queue: Any, status_queue: Any, stop_event: threading.Event) -> None:
    try:
        import cv2
    except Exception as exc:
        put_latest(
            status_queue,
            SensorStatus("camera", False, f"OpenCV missing: {exc}", time.time()),
        )
        return

    cap = None
    for idx in config.CAMERA_INDEX_CANDIDATES:
        test = cv2.VideoCapture(idx)
        if test.isOpened():
            cap = test
            put_latest(
                status_queue,
                SensorStatus("camera", True, f"Camera opened on /dev/video{idx}.", time.time()),
            )
            break
        test.release()

    if cap is None or not cap.isOpened():
        put_latest(
            status_queue,
            SensorStatus("camera", False, "Unable to open camera device.", time.time()),
        )
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, config.CAMERA_FPS)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    while not stop_event.is_set():
        ok, frame = cap.read()
        if ok:
            put_latest(frame_queue, frame)
        time.sleep(config.CAMERA_SLEEP_SEC)

    cap.release()

from __future__ import annotations

import threading
import time
from typing import Any

from . import config
from .models import SensorStatus, ToFHazard
from .queue_utils import put_latest
from .sensor_interface import get_obstacle_service


def tof_thread_worker(tof_queue: Any, status_queue: Any, stop_event: threading.Event) -> None:
    try:
        service = get_obstacle_service()
        put_latest(status_queue, SensorStatus("tof", True, "ToF online.", time.time()))
    except Exception as exc:
        put_latest(status_queue, SensorStatus("tof", False, f"ToF init failed: {exc}", time.time()))
        return

    loop_sleep = 1.0 / max(config.TOF_LOOP_HZ, 1.0)
    last_debug_print = 0.0
    while not stop_event.is_set():
        try:
            reading = service.read_once()
            now = time.time()
            if (
                config.SENSOR_DEBUG_PRINTS
                and (now - last_debug_print) >= config.TOF_DEBUG_PRINT_INTERVAL_SEC
            ):
                left = reading.distances.left_m
                center = reading.distances.center_m
                right = reading.distances.right_m
                left_str = f"{left:.2f}m" if left is not None else "None"
                center_str = f"{center:.2f}m" if center is not None else "None"
                right_str = f"{right:.2f}m" if right is not None else "None"
                print(
                    f"[TOF] zone={reading.zone} "
                    f"left={left_str} center={center_str} right={right_str}"
                )
                last_debug_print = now
            if reading.zone != "CLEAR":
                if reading.zone == "LEFT":
                    dist = reading.distances.left_m
                    direction = "10 o'clock"
                elif reading.zone == "RIGHT":
                    dist = reading.distances.right_m
                    direction = "2 o'clock"
                else:
                    dist = reading.distances.center_m
                    direction = "12 o'clock"

                put_latest(
                    tof_queue,
                    ToFHazard(
                        label="obstacle",
                        zone=reading.zone,
                        distance_m=dist,
                        priority_score=3,
                        direction=direction,
                    ),
                )
            else:
                put_latest(tof_queue, None)
        except Exception as exc:
            put_latest(status_queue, SensorStatus("tof", False, f"ToF read error: {exc}", time.time()))
            return
        time.sleep(loop_sleep)

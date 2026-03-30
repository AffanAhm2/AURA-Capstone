from __future__ import annotations

import random
import threading
import time
from typing import Any

from . import config
from .models import ImuReading, SensorStatus
from .queue_utils import put_latest


def imu_thread_worker(imu_queue: Any, status_queue: Any, stop_event: threading.Event) -> None:
    sensor = None
    try:
        from mpu6050 import mpu6050  # type: ignore

        sensor = mpu6050(0x68)
        put_latest(status_queue, SensorStatus("imu", True, "MPU-6050 online.", time.time()))
    except Exception as exc:
        if not config.IMU_MOCK_IF_UNAVAILABLE:
            put_latest(status_queue, SensorStatus("imu", False, f"IMU init failed: {exc}", time.time()))
            return
        put_latest(status_queue, SensorStatus("imu", True, "IMU mock mode active.", time.time()))

    loop_sleep = 1.0 / max(config.IMU_LOOP_HZ, 1.0)
    last_debug_print = 0.0
    while not stop_event.is_set():
        ts = time.time()
        if sensor is not None:
            try:
                accel = sensor.get_accel_data()
                gyro = sensor.get_gyro_data()
                reading = ImuReading(
                    timestamp=ts,
                    accel_xyz=(float(accel["x"]), float(accel["y"]), float(accel["z"])),
                    gyro_xyz=(float(gyro["x"]), float(gyro["y"]), float(gyro["z"])),
                )
            except Exception as exc:
                put_latest(status_queue, SensorStatus("imu", False, f"IMU read error: {exc}", time.time()))
                return
        else:
            reading = ImuReading(
                timestamp=ts,
                accel_xyz=(0.0 + random.uniform(-0.02, 0.02), 0.0, 1.0),
                gyro_xyz=(0.0, 0.0, random.uniform(-0.5, 0.5)),
            )
        put_latest(imu_queue, reading)
        if config.SENSOR_DEBUG_PRINTS and (ts - last_debug_print) >= config.IMU_DEBUG_PRINT_INTERVAL_SEC:
            ax, ay, az = reading.accel_xyz
            gx, gy, gz = reading.gyro_xyz
            print(
                f"[IMU] accel=({ax:.3f}, {ay:.3f}, {az:.3f})g "
                f"gyro=({gx:.3f}, {gy:.3f}, {gz:.3f})deg/s"
            )
            last_debug_print = ts
        time.sleep(loop_sleep)

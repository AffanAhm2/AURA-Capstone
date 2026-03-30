"""
Distance frame providers.

Each provider returns a normalized 8x8 frame in millimeters, where None means
invalid or unavailable pixel data.
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Sequence

from .config import TOF_CACHE_MS, TOF_LPN_PIN, TOF_RANGING_HZ, TOF_RESOLUTION
from .models import Frame8x8Mm

LEFT_COLUMNS = range(0, 3)
CENTER_COLUMNS = range(3, 5)
RIGHT_COLUMNS = range(5, 8)


class DistanceProvider(ABC):
    @abstractmethod
    def read_frame_mm(self) -> Frame8x8Mm:
        raise NotImplementedError


class MockDistanceProvider(DistanceProvider):
    """
    RNG provider with realistic obstacle bursts for dev/testing.
    """

    def __init__(self):
        self._counter = {"left": 0, "right": 0, "center": 0}

    def _pick_obstacle_columns(self) -> Sequence[int]:
        for key in list(self._counter):
            if self._counter[key] > 0:
                self._counter[key] -= 1

        if all(v == 0 for v in self._counter.values()):
            roll = random.random()
            if roll < 0.18:
                self._counter["left"] = random.randint(4, 9)
            elif roll < 0.36:
                self._counter["right"] = random.randint(4, 9)
            elif roll < 0.48:
                self._counter["center"] = random.randint(4, 9)

        if self._counter["left"] > 0:
            return LEFT_COLUMNS
        if self._counter["right"] > 0:
            return RIGHT_COLUMNS
        if self._counter["center"] > 0:
            return CENTER_COLUMNS
        return ()

    def read_frame_mm(self) -> Frame8x8Mm:
        obstacle_cols = self._pick_obstacle_columns()
        base_clear_mm = 2200
        frame: Frame8x8Mm = []
        for _ in range(8):
            row = []
            for col in range(8):
                if random.random() < 0.02:
                    row.append(None)
                    continue
                noise = random.randint(-80, 80)
                if obstacle_cols and col in obstacle_cols:
                    row.append(random.randint(350, 900) + noise)
                else:
                    row.append(base_clear_mm + noise)
            frame.append(row)
        return frame


class VL53L8CXProvider(DistanceProvider):
    """
    Raspberry Pi hardware provider.

    Uses the CircuitPython VL53LXCX package if available:
    - adafruit-blinka
    - circuitpython-vl53lxcx
    """

    def __init__(self):
        self._sensor = None
        self._last_frame: Optional[Frame8x8Mm] = None
        self._last_ms = 0.0
        self._init_hardware()

    @staticmethod
    def _ensure_firmware_path() -> None:
        """
        Work around the library looking for firmware in .venv/lib/python3/ instead
        of the actual site-packages directory under .venv/lib/python3.x/.
        """
        try:
            import vl53lxcx  # type: ignore
        except Exception:
            return

        package_dir = Path(vl53lxcx.__file__).resolve().parent
        source_fw = package_dir / "vl53l8cx_fw.bin"
        if not source_fw.exists():
            return

        venv_root = package_dir.parents[3]
        expected_dir = venv_root / "lib" / "python3"
        expected_fw = expected_dir / "vl53l8cx_fw.bin"
        if expected_fw.exists():
            return

        try:
            expected_dir.mkdir(parents=True, exist_ok=True)
            expected_fw.symlink_to(source_fw)
        except Exception:
            try:
                expected_fw.write_bytes(source_fw.read_bytes())
            except Exception:
                pass

    @staticmethod
    def _patch_firmware_lookup() -> None:
        """
        The vl53lxcx package can reject an existing firmware file because of its
        own path resolution logic. Override that lookup to point at the actual
        packaged firmware file.
        """
        try:
            import vl53lxcx  # type: ignore
        except Exception:
            return

        package_dir = Path(vl53lxcx.__file__).resolve().parent
        source_fw = package_dir / "vl53l8cx_fw.bin"
        if not source_fw.exists():
            return

        original_find_file = getattr(vl53lxcx, "_find_file", None)
        if original_find_file is None:
            return

        def _patched_find_file(name, expected_size):
            if str(name).endswith("vl53l8cx_fw.bin") and source_fw.exists():
                actual_size = source_fw.stat().st_size
                if expected_size is None or actual_size == expected_size:
                    return str(source_fw)
            return original_find_file(name, expected_size)

        vl53lxcx._find_file = _patched_find_file

    @staticmethod
    def _resolve_board_pin(board_module, pin_value):
        if pin_value is None:
            return None

        raw = str(pin_value).strip().upper()
        candidates = [raw]
        if raw.startswith("GPIO") and raw[4:].isdigit():
            candidates.append(f"D{raw[4:]}")
        if raw.isdigit():
            candidates.append(f"D{raw}")
            candidates.append(f"GPIO{raw}")

        for name in candidates:
            if hasattr(board_module, name):
                return getattr(board_module, name)

        raise RuntimeError(f"Invalid TOF_LPN_PIN {pin_value!r}.")

    def _init_hardware(self) -> None:
        try:
            import board
            import busio
            from vl53lxcx import (
                DATA_DISTANCE_MM,
                DATA_TARGET_STATUS,
                RESOLUTION_4X4,
                RESOLUTION_8X8,
                STATUS_VALID,
                VL53L8CX,
            )
        except Exception as exc:
            raise RuntimeError(
                "VL53L8CX dependencies missing. Install adafruit-blinka and "
                "circuitpython-vl53lxcx on Raspberry Pi."
            ) from exc

        self._ensure_firmware_path()
        self._patch_firmware_lookup()

        i2c = busio.I2C(board.SCL, board.SDA, frequency=1_000_000)
        lpn = None
        if TOF_LPN_PIN:
            lpn = self._resolve_board_pin(board, TOF_LPN_PIN)

        sensor = VL53L8CX(i2c, lpn=lpn)
        if lpn is not None and hasattr(sensor, "reset"):
            sensor.reset()
        if hasattr(sensor, "is_alive") and not sensor.is_alive():
            raise RuntimeError("VL53L8CX not detected on I2C bus.")
        sensor.init()

        if TOF_RESOLUTION.lower() == "8x8":
            if hasattr(sensor, "set_resolution"):
                sensor.set_resolution(RESOLUTION_8X8)
            else:
                sensor.resolution = RESOLUTION_8X8
        else:
            if hasattr(sensor, "set_resolution"):
                sensor.set_resolution(RESOLUTION_4X4)
            else:
                sensor.resolution = RESOLUTION_4X4

        try:
            if hasattr(sensor, "set_ranging_frequency_hz"):
                sensor.set_ranging_frequency_hz(TOF_RANGING_HZ)
            elif hasattr(sensor, "ranging_freq"):
                sensor.ranging_freq = TOF_RANGING_HZ
            else:
                sensor.ranging_frequency_hz = TOF_RANGING_HZ
        except Exception:
            pass

        sensor.start_ranging({DATA_DISTANCE_MM, DATA_TARGET_STATUS})
        self._sensor = sensor
        self._status_valid = STATUS_VALID
        print("[INIT] VL53L8CX provider initialized.")

    @staticmethod
    def _to_grid(raw_distances_mm) -> Frame8x8Mm:
        values = list(raw_distances_mm)
        if len(values) < 64:
            values = values + [None] * (64 - len(values))
        values = values[:64]

        frame: Frame8x8Mm = []
        for r in range(8):
            row = []
            for c in range(8):
                v = values[r * 8 + c]
                if v is None:
                    row.append(None)
                else:
                    try:
                        mm = int(v)
                    except Exception:
                        row.append(None)
                        continue
                    row.append(mm if mm > 0 else None)
            frame.append(row)
        return frame

    @staticmethod
    def _extract_fields(payload) -> tuple[Optional[Sequence[int]], Optional[Sequence[int]]]:
        if payload is None:
            return None, None

        distance_names = ("distance_mm", "distances_mm", "distance", "distances")
        status_names = ("target_status", "status", "statuses", "target_statuses")

        distances = None
        statuses = None

        for name in distance_names:
            if isinstance(payload, dict) and name in payload:
                distances = payload[name]
                break
            if hasattr(payload, name):
                distances = getattr(payload, name)
                break

        for name in status_names:
            if isinstance(payload, dict) and name in payload:
                statuses = payload[name]
                break
            if hasattr(payload, name):
                statuses = getattr(payload, name)
                break

        return distances, statuses

    @staticmethod
    def _empty_frame() -> Frame8x8Mm:
        return [[None for _ in range(8)] for _ in range(8)]

    def read_frame_mm(self) -> Frame8x8Mm:
        now_ms = time.time() * 1000.0
        if self._last_frame is not None and (now_ms - self._last_ms) < TOF_CACHE_MS:
            return self._last_frame

        if self._sensor is None:
            raise RuntimeError("VL53L8CX provider not initialized.")

        distances = None
        statuses = None
        deadline = time.time() + 1.0

        while time.time() < deadline and distances is None:
            ready = True
            if hasattr(self._sensor, "check_data_ready"):
                try:
                    ready = bool(self._sensor.check_data_ready())
                except Exception:
                    ready = True

            payload = None
            if ready and hasattr(self._sensor, "get_ranging_data"):
                try:
                    payload = self._sensor.get_ranging_data()
                except Exception:
                    payload = None
            if payload is None and ready and hasattr(self._sensor, "get_data"):
                try:
                    payload = self._sensor.get_data()
                except Exception:
                    payload = None
            if payload is None and hasattr(self._sensor, "data"):
                try:
                    payload = getattr(self._sensor, "data")
                except Exception:
                    payload = None

            distances, statuses = self._extract_fields(payload)

            if distances is None:
                direct_distances, direct_statuses = self._extract_fields(self._sensor)
                distances = direct_distances
                statuses = direct_statuses

            if distances is None:
                time.sleep(0.05)

        if distances is None:
            if self._last_frame is not None:
                return self._last_frame
            frame = self._empty_frame()
            self._last_frame = frame
            self._last_ms = now_ms
            return frame

        if statuses is not None:
            filtered = []
            for dist, status in zip(list(distances), list(statuses)):
                if status == getattr(self, "_status_valid", None):
                    filtered.append(dist)
                else:
                    filtered.append(None)
            distances = filtered

        frame = self._to_grid(distances)
        self._last_frame = frame
        self._last_ms = now_ms
        return frame

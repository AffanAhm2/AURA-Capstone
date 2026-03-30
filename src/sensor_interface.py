"""
Legacy compatibility wrapper for distance reads.

New code should prefer `ObstacleDetectionService` from `obstacle_service.py`.
"""

from __future__ import annotations

import time
from typing import Optional

from .config import DISTANCE_PROVIDER, TOF_LOOP_HZ
from .models import ZoneDistances
from .obstacle_service import ObstacleDetectionService
from .providers import MockDistanceProvider, VL53L8CXProvider

_service: Optional[ObstacleDetectionService] = None
_last_zones: Optional[ZoneDistances] = None


def _build_service() -> ObstacleDetectionService:
    provider_name = DISTANCE_PROVIDER.lower().strip()
    if provider_name == "vl53l8cx":
        provider = VL53L8CXProvider()
    elif provider_name == "mock":
        provider = MockDistanceProvider()
    else:
        raise ValueError(
            f"Unsupported DISTANCE_PROVIDER={DISTANCE_PROVIDER!r}. Use 'mock' or 'vl53l8cx'."
        )
    return ObstacleDetectionService(provider)


def get_obstacle_service() -> ObstacleDetectionService:
    global _service
    if _service is None:
        _service = _build_service()
    return _service


def get_zone_distances() -> ZoneDistances:
    global _last_zones
    reading = get_obstacle_service().read_once()
    _last_zones = reading.distances
    return reading.distances


def get_left_distance() -> float | None:
    zones = get_zone_distances()
    if zones.center_m is not None and (zones.left_m is None or zones.center_m < zones.left_m):
        return zones.center_m
    return zones.left_m


def get_right_distance() -> float | None:
    zones = get_zone_distances()
    if zones.center_m is not None and (zones.right_m is None or zones.center_m < zones.right_m):
        return zones.center_m
    return zones.right_m


def wait_between_reads() -> None:
    if TOF_LOOP_HZ <= 0:
        return
    time.sleep(1.0 / TOF_LOOP_HZ)

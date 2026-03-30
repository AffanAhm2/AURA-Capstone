"""
Hardware-agnostic obstacle detection service.

This module is designed to be composed with other subsystems (webcam ML,
navigation, haptics) by passing `ObstacleReading` objects around.
"""

from __future__ import annotations

import time
from typing import Callable, Optional, Sequence

from .classifier import classify_from_zones
from .models import Frame8x8Mm, ObstacleReading, ZoneDistances
from .providers import CENTER_COLUMNS, LEFT_COLUMNS, RIGHT_COLUMNS, DistanceProvider


def _min_distance_for_columns(frame: Frame8x8Mm, columns: Sequence[int]) -> Optional[float]:
    min_mm: Optional[int] = None
    for row in frame:
        for col in columns:
            value = row[col]
            if value is None:
                continue
            if min_mm is None or value < min_mm:
                min_mm = value
    return (min_mm / 1000.0) if min_mm is not None else None


class ObstacleDetectionService:
    def __init__(self, provider: DistanceProvider):
        self._provider = provider
        self._last_zone: Optional[str] = None

    def read_once(self) -> ObstacleReading:
        frame = self._provider.read_frame_mm()
        zones = ZoneDistances(
            left_m=_min_distance_for_columns(frame, LEFT_COLUMNS),
            center_m=_min_distance_for_columns(frame, CENTER_COLUMNS),
            right_m=_min_distance_for_columns(frame, RIGHT_COLUMNS),
        )
        zone = classify_from_zones(zones)
        changed = zone != self._last_zone
        self._last_zone = zone

        return ObstacleReading(
            timestamp=time.time(),
            zone=zone,
            changed=changed,
            distances=zones,
        )

    def run_tick(self, callback: Callable[[ObstacleReading], None]) -> ObstacleReading:
        """
        Run one read cycle and publish a normalized reading.
        """
        reading = self.read_once()
        callback(reading)
        return reading

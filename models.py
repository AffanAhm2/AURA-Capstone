from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple


Frame8x8Mm = List[List[Optional[int]]]


@dataclass(frozen=True)
class ZoneDistances:
    left_m: Optional[float]
    center_m: Optional[float]
    right_m: Optional[float]


@dataclass(frozen=True)
class ObstacleReading:
    timestamp: float
    zone: str
    changed: bool
    distances: ZoneDistances


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    bbox: Tuple[int, int, int, int]
    center_bias: float
    priority_score: int
    direction: str
    source: str = "vision"
    distance_m: Optional[float] = None


@dataclass(frozen=True)
class SensorStatus:
    name: str
    active: bool
    message: str
    timestamp: float


@dataclass(frozen=True)
class ImuReading:
    timestamp: float
    accel_xyz: Tuple[float, float, float]
    gyro_xyz: Tuple[float, float, float]
    source: str = "imu"


@dataclass(frozen=True)
class GpsReading:
    timestamp: float
    latitude: Optional[float]
    longitude: Optional[float]
    speed_mps: Optional[float]
    sats: Optional[int]
    source: str = "gps"


@dataclass(frozen=True)
class WifiReading:
    timestamp: float
    latitude: Optional[float]
    longitude: Optional[float]
    location_name: Optional[str]
    matched_anchor: Optional[str]
    confidence: float
    source: str = "wifi"


@dataclass
class RuntimeState:
    latest_detections: List[Detection] = field(default_factory=list)
    prev_scene: Tuple[Tuple[str, str], ...] = ()
    cycle_index: int = 0
    prev_had_detections: bool = False
    empty_streak: int = 0
    paused: bool = False
    relaxed_mode: bool = False
    last_announce_ts: float = 0.0
    last_tof_zone: Optional[str] = None
    last_tof_ts: float = 0.0
    last_imu_ts: float = 0.0
    last_gps_ts: float = 0.0
    last_wifi_ts: float = 0.0
    last_status_by_name: dict[str, SensorStatus] = field(default_factory=dict)
    tilt_state: Optional[str] = None
    tilt_candidate: Optional[str] = None
    tilt_candidate_since: float = 0.0
    last_tilt_announce_ts: float = 0.0


@dataclass(frozen=True)
class ToFHazard:
    label: str
    zone: str
    distance_m: Optional[float]
    priority_score: int
    direction: str
    source: str = "tof"

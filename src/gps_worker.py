from __future__ import annotations

import threading
import time
from typing import Any, Optional

from . import config
from .models import GpsReading, SensorStatus
from .queue_utils import put_latest


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value in ("", None):
            return None
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value in ("", None):
            return None
        return int(value)
    except Exception:
        return None


def _extract_fix(msg: Any, last_reading: Optional[GpsReading], ts: float) -> Optional[GpsReading]:
    latitude = _safe_float(getattr(msg, "latitude", None))
    longitude = _safe_float(getattr(msg, "longitude", None))
    speed_mps = last_reading.speed_mps if last_reading is not None else None
    sats = last_reading.sats if last_reading is not None else None

    spd_knots = _safe_float(getattr(msg, "spd_over_grnd", None))
    if spd_knots is not None:
        speed_mps = spd_knots * 0.514444

    msg_sats = _safe_int(getattr(msg, "num_sats", None))
    if msg_sats is not None:
        sats = msg_sats

    status = str(getattr(msg, "status", "") or "").upper()
    gps_qual = _safe_int(getattr(msg, "gps_qual", None))
    has_fix = False

    if latitude is not None and longitude is not None:
        if status in {"A", ""}:
            has_fix = True
        if gps_qual is not None and gps_qual > 0:
            has_fix = True
        if msg.__class__.__name__ in {"GGA", "GLL", "RMC", "GNS"}:
            has_fix = True

    if not has_fix and latitude is None and longitude is None:
        if speed_mps is not None or sats is not None:
            return GpsReading(
                timestamp=ts,
                latitude=last_reading.latitude if last_reading is not None else None,
                longitude=last_reading.longitude if last_reading is not None else None,
                speed_mps=speed_mps,
                sats=sats,
            )
        return None

    if not has_fix:
        return None

    return GpsReading(
        timestamp=ts,
        latitude=latitude,
        longitude=longitude,
        speed_mps=speed_mps,
        sats=sats,
    )


def _read_gpsd_fix(client: Any, ts: float) -> Optional[GpsReading]:
    packet = client.get_current()
    mode = int(getattr(packet, "mode", 0) or 0)
    if mode < 2:
        sats = _safe_int(getattr(packet, "sats", None))
        return GpsReading(ts, None, None, None, sats)

    lat = _safe_float(getattr(packet, "lat", None))
    lon = _safe_float(getattr(packet, "lon", None))
    speed = _safe_float(getattr(packet, "hspeed", None))
    if speed is None:
        speed = _safe_float(getattr(packet, "speed", None))
    sats = _safe_int(getattr(packet, "sats", None))
    return GpsReading(ts, lat, lon, speed, sats)


def gps_thread_worker(gps_queue: Any, status_queue: Any, stop_event: threading.Event) -> None:
    gpsd_client = None
    ser = None
    parser = None
    last_real_reading: Optional[GpsReading] = None
    source_name = "gpsd"

    try:
        import gpsd  # type: ignore

        gpsd.connect()
        gpsd_client = gpsd
        put_latest(status_queue, SensorStatus("gps", True, "GPS via gpsd online.", time.time()))
    except Exception as gpsd_exc:
        try:
            import serial  # type: ignore
            import pynmea2  # type: ignore

            ser = serial.Serial(config.GPS_SERIAL_PORT, config.GPS_BAUDRATE, timeout=1)
            parser = pynmea2
            source_name = "serial"
            put_latest(
                status_queue,
                SensorStatus("gps", True, f"GPS serial online. gpsd unavailable: {gpsd_exc}", time.time()),
            )
        except Exception as serial_exc:
            if not config.GPS_MOCK_IF_UNAVAILABLE:
                put_latest(
                    status_queue,
                    SensorStatus(
                        "gps",
                        False,
                        f"GPS init failed: gpsd={gpsd_exc}; serial={serial_exc}",
                        time.time(),
                    ),
                )
                return
            put_latest(status_queue, SensorStatus("gps", True, "GPS mock mode active.", time.time()))

    loop_sleep = 1.0 / max(config.GPS_LOOP_HZ, 0.2)
    last_debug_print = 0.0

    while not stop_event.is_set():
        ts = time.time()
        reading = None

        if gpsd_client is not None:
            try:
                reading = _read_gpsd_fix(gpsd_client, ts)
                if reading.latitude is not None and reading.longitude is not None:
                    last_real_reading = reading
            except Exception:
                reading = None
        elif ser is not None and parser is not None:
            try:
                line = ser.readline().decode("ascii", errors="ignore").strip()
                if line.startswith("$"):
                    msg = parser.parse(line)
                    reading = _extract_fix(msg, last_real_reading, ts)
                    if reading is not None and reading.latitude is not None and reading.longitude is not None:
                        last_real_reading = reading
            except Exception:
                reading = None

        if reading is None:
            if last_real_reading is not None:
                reading = GpsReading(
                    timestamp=ts,
                    latitude=last_real_reading.latitude,
                    longitude=last_real_reading.longitude,
                    speed_mps=last_real_reading.speed_mps,
                    sats=last_real_reading.sats,
                )
            else:
                reading = GpsReading(
                    timestamp=ts,
                    latitude=None,
                    longitude=None,
                    speed_mps=None,
                    sats=None,
                )

        put_latest(gps_queue, reading)
        if config.SENSOR_DEBUG_PRINTS and (ts - last_debug_print) >= config.GPS_DEBUG_PRINT_INTERVAL_SEC:
            lat = f"{reading.latitude:.6f}" if reading.latitude is not None else "None"
            lon = f"{reading.longitude:.6f}" if reading.longitude is not None else "None"
            speed = f"{reading.speed_mps:.2f}m/s" if reading.speed_mps is not None else "None"
            sats = reading.sats if reading.sats is not None else "None"
            source = source_name if last_real_reading is not None else f"{source_name}-no-fix"
            print(f"[GPS] source={source} lat={lat} lon={lon} speed={speed} sats={sats}")
            last_debug_print = ts
        time.sleep(loop_sleep)

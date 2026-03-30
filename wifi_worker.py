from __future__ import annotations

import re
import subprocess
import threading
import time
from typing import Any

from . import config
from .models import SensorStatus, WifiReading
from .queue_utils import put_latest


def _run_scan() -> str:
    commands = [
        [
            "nmcli",
            "-t",
            "-f",
            "IN-USE,SSID,BSSID,SIGNAL",
            "dev",
            "wifi",
            "list",
            "ifname",
            config.WIFI_POSITION_INTERFACE,
        ],
        [
            "iw",
            "dev",
            config.WIFI_POSITION_INTERFACE,
            "scan",
        ],
    ]

    for command in commands:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except Exception:
            continue
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    raise RuntimeError("Wi-Fi scan failed. nmcli/iw unavailable or interface inaccessible.")


def _parse_scan_output(text: str) -> list[dict[str, Any]]:
    if "BSS " in text and "signal:" in text:
        networks: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("BSS "):
                if current:
                    networks.append(current)
                bssid = line.split()[1].split("(")[0].strip()
                current = {"bssid": bssid.lower(), "ssid": "", "signal": 0.0}
            elif current is not None and line.startswith("SSID:"):
                current["ssid"] = line.split("SSID:", 1)[1].strip()
            elif current is not None and line.startswith("signal:"):
                match = re.search(r"signal:\s*(-?\d+(?:\.\d+)?)", line)
                if match:
                    current["signal"] = float(match.group(1))
        if current:
            networks.append(current)
        return networks

    networks = []
    for line in text.splitlines():
        parts = line.strip().split(":")
        if len(parts) < 5:
            continue
        in_use = parts[0]
        ssid = parts[1]
        bssid = ":".join(parts[2:8]).lower() if len(parts) >= 8 else parts[2].lower()
        signal_str = parts[-1]
        try:
            signal = float(signal_str)
        except Exception:
            signal = 0.0
        if in_use == "*" or ssid or bssid:
            networks.append({"ssid": ssid, "bssid": bssid, "signal": signal})
    return networks


def _match_anchor(networks: list[dict[str, Any]]) -> WifiReading:
    best_name = None
    best_anchor = None
    best_score = 0.0
    best_lat = None
    best_lon = None
    normalized_networks = [
        {
            "ssid": str(n.get("ssid", "")).strip().lower(),
            "bssid": str(n.get("bssid", "")).strip().lower(),
            "signal": float(n.get("signal", 0.0)),
        }
        for n in networks
    ]

    for anchor_name, anchor in config.WIFI_POSITION_ANCHORS.items():
        anchor_ssid = str(anchor.get("ssid", "")).strip().lower()
        anchor_bssid = str(anchor.get("bssid", "")).strip().lower()
        for network in normalized_networks:
            ssid_match = bool(anchor_ssid) and network["ssid"] == anchor_ssid
            bssid_match = bool(anchor_bssid) and network["bssid"] == anchor_bssid
            if not ssid_match and not bssid_match:
                continue

            raw_signal = network["signal"]
            if raw_signal > 0:
                confidence = min(max(raw_signal / 100.0, 0.0), 1.0)
            else:
                confidence = min(max((raw_signal + 90.0) / 60.0, 0.0), 1.0)
            if bssid_match:
                confidence = min(confidence + 0.2, 1.0)

            if confidence > best_score:
                best_score = confidence
                best_name = anchor.get("location_name") or anchor_name
                best_anchor = anchor_name
                best_lat = anchor.get("latitude")
                best_lon = anchor.get("longitude")

    ts = time.time()
    if best_score < config.WIFI_POSITION_MIN_CONFIDENCE:
        return WifiReading(ts, None, None, None, None, best_score)
    return WifiReading(ts, best_lat, best_lon, str(best_name), best_anchor, best_score)


def wifi_position_thread_worker(wifi_queue: Any, status_queue: Any, stop_event: threading.Event) -> None:
    put_latest(status_queue, SensorStatus("wifi", True, "Wi-Fi positioning online.", time.time()))
    loop_sleep = 1.0 / max(config.WIFI_POSITION_LOOP_HZ, 0.1)
    last_debug_print = 0.0

    while not stop_event.is_set():
        ts = time.time()
        try:
            scan_output = _run_scan()
            reading = _match_anchor(_parse_scan_output(scan_output))
            put_latest(wifi_queue, reading)
        except Exception as exc:
            put_latest(status_queue, SensorStatus("wifi", False, f"Wi-Fi position scan failed: {exc}", ts))
            reading = WifiReading(ts, None, None, None, None, 0.0)
            put_latest(wifi_queue, reading)

        if config.SENSOR_DEBUG_PRINTS and (ts - last_debug_print) >= config.WIFI_DEBUG_PRINT_INTERVAL_SEC:
            lat = f"{reading.latitude:.6f}" if reading.latitude is not None else "None"
            lon = f"{reading.longitude:.6f}" if reading.longitude is not None else "None"
            print(
                f"[WIFI] lat={lat} lon={lon} location={reading.location_name or 'None'} "
                f"anchor={reading.matched_anchor or 'None'} confidence={reading.confidence:.2f}"
            )
            last_debug_print = ts
        time.sleep(loop_sleep)

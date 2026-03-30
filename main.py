"""
AURA runtime orchestrator.

Workers are split into dedicated modules for easier team collaboration.
"""

from __future__ import annotations

import csv
import multiprocessing as mp
import os
import queue
import threading
import time
from typing import Any, Optional, Sequence

from . import config
from .audio_worker import audio_process_worker
from .camera_worker import camera_thread_worker
from .feedback import speak_text
from .gpio_controls import ButtonState, setup_buttons
from .gps_worker import gps_thread_worker
from .imu_worker import imu_thread_worker
from .models import Detection, GpsReading, ImuReading, RuntimeState, SensorStatus, ToFHazard, WifiReading
from .navigation import GraphHopperClient, NavigationSession, get_destination, list_destination_names
from .navigation_speech import resolve_startup_goal
from .queue_utils import drain_all, drain_latest, put_latest
from .tof_worker import tof_thread_worker
from .vision_worker import vision_process_worker
from .wifi_worker import wifi_position_thread_worker


def _make_scene_signature(detections: Sequence[Detection]) -> tuple[tuple[str, str], ...]:
    return tuple((d.label, d.direction) for d in detections[:2])


def _rank_detections(detections: Sequence[Detection]) -> list[Detection]:
    return sorted(detections, key=lambda d: (-d.priority_score, d.center_bias, -d.confidence))


def _format_detection_announcement(detection: Detection) -> str:
    if detection.source in {"tof", "vision_tof"}:
        if detection.source == "vision_tof":
            if detection.distance_m is None:
                return f"{detection.label} {detection.direction}"
            return f"{detection.label} {detection.direction}, {detection.distance_m:.1f} meters"
        if detection.distance_m is None:
            return f"object {detection.direction}"
        return f"object {detection.distance_m:.1f} meters {detection.direction}"
    return f"{detection.label} {detection.direction}"


def _tof_matches_direction(zone: str, direction: str) -> bool:
    direction = direction.strip().lower()
    if zone == "CENTER":
        return direction in {"11 o'clock", "12 o'clock", "1 o'clock"}
    if zone == "LEFT":
        return direction in {"10 o'clock", "11 o'clock"}
    if zone == "RIGHT":
        return direction in {"1 o'clock", "2 o'clock"}
    return False


def _tof_priority_bonus(distance_m: Optional[float]) -> int:
    if distance_m is None:
        return 0
    if distance_m <= 0.5:
        return 3
    if distance_m <= 1.0:
        return 2
    if distance_m <= 1.5:
        return 1
    return 0


def _fuse_tof_with_detections(
    detections: Sequence[Detection],
    tof_hazard: Optional[ToFHazard],
) -> list[Detection]:
    fused: list[Detection] = [d for d in detections]
    if tof_hazard is None:
        return fused

    matched_idx = None
    best_bias = None
    for idx, detection in enumerate(fused):
        if _tof_matches_direction(tof_hazard.zone, detection.direction):
            if best_bias is None or detection.center_bias < best_bias:
                matched_idx = idx
                best_bias = detection.center_bias

    if matched_idx is not None:
        detection = fused[matched_idx]
        fused[matched_idx] = Detection(
            label=detection.label,
            confidence=detection.confidence,
            bbox=detection.bbox,
            center_bias=detection.center_bias,
            priority_score=max(detection.priority_score, tof_hazard.priority_score) + _tof_priority_bonus(tof_hazard.distance_m),
            direction=detection.direction,
            source="vision_tof",
            distance_m=tof_hazard.distance_m,
        )
        return fused

    fused.append(
        Detection(
            label=f"{tof_hazard.label} {tof_hazard.zone.lower()}",
            confidence=1.0,
            bbox=(0, 0, 0, 0),
            center_bias=0.0 if tof_hazard.direction == "12 o'clock" else 0.2,
            priority_score=tof_hazard.priority_score + _tof_priority_bonus(tof_hazard.distance_m),
            direction=tof_hazard.direction,
            source="tof",
            distance_m=tof_hazard.distance_m,
        )
    )
    return fused


def _classify_tilt(reading: ImuReading) -> Optional[str]:
    if not config.IMU_TILT_ALERTS_ENABLED:
        return None

    ax, ay, _ = reading.accel_xyz
    abs_x = abs(ax)
    abs_y = abs(ay)
    threshold = config.IMU_TILT_AXIS_THRESHOLD
    strong = config.IMU_TILT_STRONG_THRESHOLD

    if abs_x < threshold and abs_y < threshold:
        return None

    if abs_x >= abs_y:
        direction = "up" if ax > 0 else "down"
        if abs_x >= strong:
            return f"device tilted too far {direction}"
        return f"device tilted {direction}"

    direction = "right" if ay > 0 else "left"
    if abs_y >= strong:
        return f"device tilted too far {direction}"
    return f"device tilted {direction}"


def _consume_tilt_alert(state: RuntimeState, reading: Optional[ImuReading], now: float) -> Optional[str]:
    if reading is None or not config.IMU_TILT_ALERTS_ENABLED:
        return None

    candidate = _classify_tilt(reading)
    if candidate != state.tilt_candidate:
        state.tilt_candidate = candidate
        state.tilt_candidate_since = now

    if candidate is None:
        state.tilt_state = None
        return None

    if (now - state.tilt_candidate_since) < config.IMU_TILT_PERSIST_SEC:
        return None

    if candidate == state.tilt_state and (now - state.last_tilt_announce_ts) < config.IMU_TILT_ANNOUNCE_COOLDOWN_SEC:
        return None

    state.tilt_state = candidate
    state.last_tilt_announce_ts = now
    return candidate


def _log_status(status_queue: Any) -> None:
    for st in drain_all(status_queue):
        if isinstance(st, SensorStatus):
            state = "ACTIVE" if st.active else "INACTIVE"
            print(f"[STATUS] {st.name} {state}: {st.message}")


def _compose_announcement(
    sorted_dets: Sequence[Detection],
    state: RuntimeState,
    now: float,
) -> Optional[str]:
    interval = (
        config.ANNOUNCE_RELAXED_INTERVAL_SEC
        if state.relaxed_mode
        else config.ANNOUNCE_NORMAL_INTERVAL_SEC
    )
    if (now - state.last_announce_ts) < interval:
        return None

    state.last_announce_ts = now
    scene = _make_scene_signature(sorted_dets)

    if sorted_dets:
        top_changed = bool(state.prev_scene) and scene and scene[0] != state.prev_scene[0]
        if top_changed:
            state.cycle_index = 0
        state.prev_scene = scene
        state.prev_had_detections = True
        state.empty_streak = 0

        msg = None
        if state.cycle_index == 0 and len(sorted_dets) >= 1:
            msg = _format_detection_announcement(sorted_dets[0])
        elif state.cycle_index == 1 and len(sorted_dets) >= 2:
            msg = _format_detection_announcement(sorted_dets[1])
        state.cycle_index = (state.cycle_index + 1) % 4
        return msg

    state.empty_streak += 1
    state.cycle_index = 0
    state.prev_scene = ()
    if state.prev_had_detections and state.empty_streak >= config.ANNOUNCE_EMPTY_STREAK_REQUIRED:
        state.prev_had_detections = False
        state.empty_streak = 0
        return "path clear"
    return None


def _open_log_file():
    if not config.LOGGING_ENABLED:
        return None, None
    is_new_file = not os.path.exists(config.LOG_FILE_NAME)
    file_handle = open(config.LOG_FILE_NAME, "a", newline="", encoding="utf-8")
    writer = csv.writer(file_handle)
    if is_new_file:
        writer.writerow(
            [
                "timestamp",
                "paused",
                "relaxed_mode",
                "detection_count",
                "top_label",
                "top_direction",
                "tof_zone",
                "imu_age_s",
                "gps_age_s",
            ]
        )
    return file_handle, writer


def _announce(msg: str, audio_q: Any):
    if config.AUDIO_PROCESS_ENABLED and audio_q is not None:
        put_latest(audio_q, msg)
    else:
        speak_text(msg)
    print(f"[ANNOUNCE] {msg}")


def _nav_focus_active(start_ts: float, route_started: bool, nav_failed: bool) -> bool:
    if not config.NAVIGATION_ENABLED:
        return False
    if route_started or nav_failed:
        return False
    return (time.time() - start_ts) < config.NAVIGATION_STARTUP_FOCUS_SEC


def _resolve_position_source(gps_reading: Any, wifi_reading: Any) -> tuple[Optional[float], Optional[float], str]:
    if (
        isinstance(gps_reading, GpsReading)
        and gps_reading.latitude is not None
        and gps_reading.longitude is not None
    ):
        return gps_reading.latitude, gps_reading.longitude, "gps"
    if (
        isinstance(wifi_reading, WifiReading)
        and wifi_reading.latitude is not None
        and wifi_reading.longitude is not None
    ):
        return wifi_reading.latitude, wifi_reading.longitude, "wifi"
    return None, None, "none"


def main():
    print("AURA unified runtime (modular independent components)")
    print("Press Ctrl+C to stop.\n")

    frame_queue: queue.Queue[Any] = queue.Queue(maxsize=1)
    tof_queue: queue.Queue[Any] = queue.Queue(maxsize=1)
    imu_queue: queue.Queue[Any] = queue.Queue(maxsize=1)
    gps_queue: queue.Queue[Any] = queue.Queue(maxsize=1)
    wifi_queue: queue.Queue[Any] = queue.Queue(maxsize=1)

    mp_ctx = mp.get_context("spawn")
    vision_input_q = mp_ctx.Queue(maxsize=1)
    vision_output_q = mp_ctx.Queue(maxsize=1)
    audio_q = mp_ctx.Queue(maxsize=1)
    status_q = mp_ctx.Queue(maxsize=16)

    thread_stop = threading.Event()
    process_stop = mp_ctx.Event()
    threads: list[threading.Thread] = []
    processes: list[mp.Process] = []
    state = RuntimeState()
    button_state = ButtonState()

    gpio_mod = setup_buttons(status_q, button_state)

    if config.CAMERA_ENABLED:
        t = threading.Thread(target=camera_thread_worker, args=(frame_queue, status_q, thread_stop), daemon=True)
        threads.append(t)
        t.start()
    if config.TOF_ENABLED:
        t = threading.Thread(target=tof_thread_worker, args=(tof_queue, status_q, thread_stop), daemon=True)
        threads.append(t)
        t.start()
    if config.IMU_ENABLED:
        t = threading.Thread(target=imu_thread_worker, args=(imu_queue, status_q, thread_stop), daemon=True)
        threads.append(t)
        t.start()
    if config.GPS_ENABLED:
        t = threading.Thread(target=gps_thread_worker, args=(gps_queue, status_q, thread_stop), daemon=True)
        threads.append(t)
        t.start()
    if config.WIFI_POSITION_ENABLED:
        t = threading.Thread(target=wifi_position_thread_worker, args=(wifi_queue, status_q, thread_stop), daemon=True)
        threads.append(t)
        t.start()

    if config.VISION_ENABLED:
        p = mp_ctx.Process(
            target=vision_process_worker,
            args=(vision_input_q, vision_output_q, status_q, process_stop),
            daemon=True,
        )
        processes.append(p)
        p.start()
    if config.AUDIO_PROCESS_ENABLED:
        p = mp_ctx.Process(
            target=audio_process_worker,
            args=(audio_q, status_q, process_stop),
            daemon=True,
        )
        processes.append(p)
        p.start()

    nav_session: Optional[NavigationSession] = None
    nav_destination = None
    nav_route_started = False
    nav_last_waiting_announce_ts = 0.0
    nav_last_error_announce_ts = 0.0
    nav_failed = False
    nav_last_route_attempt_ts = 0.0
    nav_boot_ts = time.time()
    last_gps_reading: Optional[GpsReading] = None
    last_wifi_reading: Optional[WifiReading] = None
    if config.NAVIGATION_ENABLED:
        goal = resolve_startup_goal(audio_q, status_q, "", list_destination_names())
        nav_destination = get_destination(goal)
        if nav_destination is None:
            put_latest(
                status_q,
                SensorStatus("navigation", False, f"Unknown destination: {goal}", time.time()),
            )
            nav_failed = True
        else:
            put_latest(
                status_q,
                SensorStatus(
                    "navigation",
                    True,
                    f"Destination selected: {nav_destination.name}. Waiting for GPS fix.",
                    time.time(),
                ),
            )

    log_file, log_writer = _open_log_file()
    loop_sleep = 1.0 / max(config.MAIN_LOOP_HZ, 1.0)

    try:
        while True:
            now = time.time()
            _log_status(status_q)

            pause_toggle, mode_toggle = button_state.pop_flags()
            if pause_toggle:
                state.paused = not state.paused
                print(f"[MODE] paused={state.paused}")
            if mode_toggle:
                state.relaxed_mode = not state.relaxed_mode
                print(f"[MODE] relaxed={state.relaxed_mode}")

            if state.paused:
                drain_latest(frame_queue)
                drain_latest(vision_input_q)
                drain_latest(vision_output_q)
                drain_latest(audio_q)
                time.sleep(loop_sleep)
                continue

            frame = drain_latest(frame_queue)
            if frame is not None and config.VISION_ENABLED:
                put_latest(vision_input_q, frame)

            dets = drain_latest(vision_output_q)
            if dets is not None:
                state.latest_detections = list(dets)

            tof_hazard = drain_latest(tof_queue)
            if isinstance(tof_hazard, ToFHazard):
                state.last_tof_zone = tof_hazard.zone
                state.last_tof_ts = now

            imu_reading = drain_latest(imu_queue)
            if isinstance(imu_reading, ImuReading):
                state.last_imu_ts = imu_reading.timestamp

            gps_reading = drain_latest(gps_queue)
            if isinstance(gps_reading, GpsReading):
                state.last_gps_ts = gps_reading.timestamp
                last_gps_reading = gps_reading
            wifi_reading = drain_latest(wifi_queue)
            if isinstance(wifi_reading, WifiReading):
                state.last_wifi_ts = wifi_reading.timestamp
                last_wifi_reading = wifi_reading

            if config.NAVIGATION_ENABLED and not nav_failed and nav_destination is not None and not nav_route_started:
                nav_lat, nav_lon, nav_source = _resolve_position_source(last_gps_reading, last_wifi_reading)
                has_fix = nav_lat is not None and nav_lon is not None
                if has_fix:
                    if (now - nav_last_route_attempt_ts) >= config.NAVIGATION_ROUTE_RETRY_SEC:
                        nav_last_route_attempt_ts = now
                        try:
                            client = GraphHopperClient(
                                config.NAVIGATION_GRAPHHOPPER_URL,
                                profile=config.NAVIGATION_GRAPHHOPPER_PROFILE,
                            )
                            route_plan = client.route(
                                nav_lat,
                                nav_lon,
                                nav_destination,
                            )
                            nav_session = NavigationSession(
                                route_plan,
                                step_trigger_radius_m=config.NAVIGATION_ROUTE_STEP_TRIGGER_M,
                                arrival_radius_m=config.NAVIGATION_ARRIVAL_RADIUS_M,
                            )
                            nav_route_started = True
                            _announce(nav_session.start_message(), audio_q)
                            put_latest(
                                status_q,
                                SensorStatus(
                                    "navigation",
                                    True,
                                    f"Route ready to {nav_destination.name} using {nav_source}.",
                                    time.time(),
                                ),
                            )
                        except Exception as exc:
                            put_latest(
                                status_q,
                                SensorStatus(
                                    "navigation",
                                    False,
                                    f"Route request failed, retrying: {exc}",
                                    time.time(),
                                ),
                            )
                            if (now - nav_last_error_announce_ts) >= config.NAVIGATION_WAITING_ANNOUNCE_SEC:
                                _announce("Route server unavailable. Waiting to retry navigation.", audio_q)
                                nav_last_error_announce_ts = now
                elif (now - nav_last_waiting_announce_ts) >= config.NAVIGATION_WAITING_ANNOUNCE_SEC:
                    _announce(f"Waiting for GPS or Wi-Fi position for navigation to {nav_destination.name}.", audio_q)
                    nav_last_waiting_announce_ts = now

            merged = _fuse_tof_with_detections(
                state.latest_detections,
                tof_hazard if isinstance(tof_hazard, ToFHazard) else None,
            )

            ranked = _rank_detections(merged)
            tilt_msg = _consume_tilt_alert(state, imu_reading if isinstance(imu_reading, ImuReading) else None, now)
            nav_msg = None
            if (
                nav_session is not None
                and nav_session.active
            ):
                nav_lat, nav_lon, _ = _resolve_position_source(last_gps_reading, last_wifi_reading)
                if nav_lat is not None and nav_lon is not None:
                    nav_msg = nav_session.update_position(
                        nav_lat,
                        nav_lon,
                    )
            focus_mode = (
                config.NAVIGATION_SUPPRESS_OTHER_ANNOUNCEMENTS_DURING_STARTUP
                and _nav_focus_active(nav_boot_ts, nav_route_started, nav_failed)
            )
            msg = None if focus_mode else _compose_announcement(ranked, state, now)
            if tilt_msg:
                if not focus_mode:
                    _announce(tilt_msg, audio_q)
            if nav_msg:
                _announce(nav_msg, audio_q)
            elif msg:
                _announce(msg, audio_q)

            if log_writer is not None:
                top = ranked[0] if ranked else None
                imu_age = (now - state.last_imu_ts) if state.last_imu_ts else None
                gps_age = (now - state.last_gps_ts) if state.last_gps_ts else None
                log_writer.writerow(
                    [
                        now,
                        state.paused,
                        state.relaxed_mode,
                        len(ranked),
                        top.label if top else "",
                        top.direction if top else "",
                        state.last_tof_zone or "",
                        f"{imu_age:.3f}" if imu_age is not None else "",
                        f"{gps_age:.3f}" if gps_age is not None else "",
                    ]
                )

            if config.DISPLAY_ENABLED and frame is not None:
                try:
                    import cv2

                    for d in state.latest_detections:
                        x1, y1, x2, y2 = d.bbox
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 0), 2)
                        cv2.putText(
                            frame,
                            f"{d.label} {d.confidence:.2f}",
                            (x1, max(10, y1 - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (0, 255, 0),
                            1,
                        )
                    cv2.imshow("AURA Debug", frame)
                    cv2.waitKey(1)
                except Exception:
                    pass

            time.sleep(loop_sleep)
    except KeyboardInterrupt:
        print("\nStopping AURA runtime.")
    finally:
        thread_stop.set()
        process_stop.set()

        for p in processes:
            p.join(timeout=1.5)
            if p.is_alive():
                p.terminate()
        for t in threads:
            t.join(timeout=0.5)

        if gpio_mod is not None:
            try:
                gpio_mod.cleanup()
            except Exception:
                pass

        if log_file is not None:
            log_file.close()
            print(f"[LOG] Data written to {config.LOG_FILE_NAME}")


if __name__ == "__main__":
    main()

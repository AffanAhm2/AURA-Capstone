from __future__ import annotations

import threading
import time
from typing import Any

from . import config
from .models import SensorStatus
from .queue_utils import put_latest


class ButtonState:
    def __init__(self):
        self.pause_toggled = False
        self.mode_toggled = False
        self._lock = threading.Lock()

    def toggle_pause(self):
        with self._lock:
            self.pause_toggled = True

    def toggle_mode(self):
        with self._lock:
            self.mode_toggled = True

    def pop_flags(self) -> tuple[bool, bool]:
        with self._lock:
            p = self.pause_toggled
            m = self.mode_toggled
            self.pause_toggled = False
            self.mode_toggled = False
            return p, m


def setup_buttons(status_queue: Any, button_state: ButtonState):
    if not config.GPIO_BUTTONS_ENABLED:
        return None
    try:
        import RPi.GPIO as GPIO  # type: ignore
    except Exception as exc:
        put_latest(status_queue, SensorStatus("buttons", False, f"GPIO unavailable: {exc}", time.time()))
        return None

    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(config.PAUSE_BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(config.MODE_BUTTON_GPIO, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    except Exception as exc:
        put_latest(
            status_queue,
            SensorStatus(
                "buttons",
                False,
                f"GPIO init failed: {exc}. Buttons disabled.",
                time.time(),
            ),
        )
        try:
            GPIO.cleanup()
        except Exception:
            pass
        return None

    def pause_cb(_: int):
        button_state.toggle_pause()

    def mode_cb(_: int):
        button_state.toggle_mode()

    try:
        GPIO.add_event_detect(
            config.PAUSE_BUTTON_GPIO,
            GPIO.FALLING,
            callback=pause_cb,
            bouncetime=config.BUTTON_BOUNCE_MS,
        )
        GPIO.add_event_detect(
            config.MODE_BUTTON_GPIO,
            GPIO.FALLING,
            callback=mode_cb,
            bouncetime=config.BUTTON_BOUNCE_MS,
        )
    except Exception as exc:
        put_latest(
            status_queue,
            SensorStatus(
                "buttons",
                False,
                f"GPIO event setup failed: {exc}. Buttons disabled.",
                time.time(),
            ),
        )
        try:
            GPIO.cleanup()
        except Exception:
            pass
        return None
    put_latest(status_queue, SensorStatus("buttons", True, "Pause/mode buttons online.", time.time()))
    return GPIO

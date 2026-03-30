from __future__ import annotations

import time
from typing import Any, Iterable, Optional

from . import config
from .feedback import speak_text
from .models import SensorStatus
from .queue_utils import put_latest


def _announce(text: str, audio_q: Any) -> None:
    if config.AUDIO_PROCESS_ENABLED and audio_q is not None:
        put_latest(audio_q, text)
    else:
        speak_text(text)
    print(f"[NAV] {text}")


def _normalize_goal(text: str, destinations: Iterable[str]) -> Optional[str]:
    normalized = (text or "").strip().lower()
    if not normalized:
        return None

    alias_map = {k.lower(): v for k, v in config.NAVIGATION_DESTINATION_ALIASES.items()}
    for phrase, destination in alias_map.items():
        if phrase in normalized and destination in destinations:
            return destination

    for destination in destinations:
        if destination.lower() in normalized:
            return destination

    return None


def _find_microphone_index(sr: Any) -> Optional[int]:
    hint = (config.NAVIGATION_SPEECH_MIC_NAME_HINT or "").strip().lower()
    if not hint:
        return None

    try:
        names = sr.Microphone.list_microphone_names()
    except Exception:
        return None

    for idx, name in enumerate(names):
        if hint in str(name).lower():
            return idx
    return None


def _recognize_once() -> Optional[str]:
    try:
        import speech_recognition as sr  # type: ignore
    except Exception:
        return None

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = config.NAVIGATION_SPEECH_ENERGY_THRESHOLD
    recognizer.dynamic_energy_threshold = True
    mic_index = _find_microphone_index(sr)

    try:
        with sr.Microphone(device_index=mic_index, sample_rate=16000) as source:
            recognizer.adjust_for_ambient_noise(
                source,
                duration=config.NAVIGATION_SPEECH_AMBIENT_SEC,
            )
            audio = recognizer.listen(
                source,
                timeout=config.NAVIGATION_SPEECH_TIMEOUT_SEC,
                phrase_time_limit=config.NAVIGATION_SPEECH_PHRASE_SEC,
            )
    except Exception:
        return None

    try:
        return recognizer.recognize_sphinx(audio)
    except Exception:
        return None


def resolve_startup_goal(
    audio_q: Any,
    status_q: Any,
    start_node: str,
    destinations: list[str],
) -> str:
    default_goal = config.NAVIGATION_DEFAULT_GOAL
    if default_goal not in destinations:
        default_goal = destinations[0] if destinations else start_node

    if not config.NAVIGATION_SPEECH_AT_START:
        put_latest(
            status_q,
            SensorStatus(
                "navigation",
                True,
                f"Navigation ready. Using default goal {default_goal}.",
                time.time(),
            ),
        )
        return default_goal

    prompt = "Say your destination now."
    _announce(prompt, audio_q)
    time.sleep(config.NAVIGATION_SPEECH_PROMPT_LEAD_SEC)
    recognized_text = _recognize_once()
    goal = _normalize_goal(recognized_text or "", destinations)

    if goal is not None:
        put_latest(
            status_q,
            SensorStatus(
                "navigation",
                True,
                f"Speech destination recognized: {goal}.",
                time.time(),
            ),
        )
        return goal

    put_latest(
        status_q,
        SensorStatus(
            "navigation",
            True,
            f"Speech destination unavailable. Falling back to {default_goal}.",
            time.time(),
        ),
    )
    return default_goal

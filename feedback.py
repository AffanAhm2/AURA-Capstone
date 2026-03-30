"""
Cross-platform feedback module for AURA.

Uses pyttsx3 in a background thread to avoid blocking the main loop and
de-duplicates identical messages to keep TTS from spamming.
"""

from __future__ import annotations

import platform
import queue
import threading
from typing import Any, Callable

from .config import USE_TTS

_speak_queue: "queue.Queue[str]" = queue.Queue()
_speaker_thread: threading.Thread | None = None
_tts_idle = threading.Event()
_tts_idle.set()


def _make_speaker() -> Callable[[str], None]:
    """
    Build a platform-specific speak function.
    Runs inside the worker thread so engines stay single-threaded.
    """
    system = platform.system()

    if system == "Windows":
        try:
            import win32com.client as wincl

            sapi = wincl.Dispatch("SAPI.SpVoice")
            try:
                sapi.Rate = 2  # speed up slightly
            except Exception:
                pass
            print("[INIT] Windows SAPI TTS engine initialized.")

            def speak(text: str) -> None:
                sapi.Speak(text)

            return speak
        except Exception as exc:  # pragma: no cover - diagnostic path
            print(f"[WARN] Failed to init SAPI TTS: {exc}")

    # Fallback: pyttsx3 cross-platform (Linux/RPi or Windows if SAPI fails)
    try:
        import pyttsx3

        engine = pyttsx3.init()
        try:
            engine.setProperty("rate", 200)  # faster speech
        except Exception:
            pass
        print("[INIT] pyttsx3 TTS engine initialized.")

        def speak(text: str) -> None:
            engine.say(text)
            engine.runAndWait()

        return speak
    except Exception as exc:  # pragma: no cover - diagnostic path
        print(f"[WARN] Failed to initialize pyttsx3: {exc}")

    # Last resort: no-op speaker to keep app alive
    def noop(_: str) -> None:
        return

    return noop


def _tts_worker():
    speaker = _make_speaker()
    while True:
        text = _speak_queue.get()
        if text is None:  # sentinel unused but kept for safety
            break
        try:
            _tts_idle.clear()
            speaker(text)
        except Exception as exc:  # pragma: no cover - diagnostic path
            print(f"[WARN] TTS speak error: {exc}")
        finally:
            if _speak_queue.empty():
                _tts_idle.set()


def _ensure_worker():
    global _speaker_thread
    if not USE_TTS:
        print("[INFO] TTS disabled; print-only feedback.")
        return
    if _speaker_thread is None:
        try:
            _speaker_thread = threading.Thread(target=_tts_worker, daemon=True)
            _speaker_thread.start()
        except Exception as exc:  # pragma: no cover - diagnostic path
            print(f"[WARN] Failed to start TTS worker: {exc}")
            _speaker_thread = None


def _queue_speech(text: str):
    if not USE_TTS:
        return
    if _speaker_thread is None:
        _ensure_worker()
        if _speaker_thread is None:
            return
    _tts_idle.clear()
    _speak_queue.put(text)


def give_feedback(zone: str, speak: bool = True) -> str:
    """
    Called only when the zone changes.
    If speak=False, only prints and returns the message.
    """
    if zone == "CLEAR":
        msg = "Clear"
    elif zone == "LEFT":
        msg = "Left obstacle"
    elif zone == "RIGHT":
        msg = "Right obstacle"
    elif zone == "CENTER":
        msg = "Ahead obstacle"
    else:
        msg = f"Unknown zone {zone}"

    print(f"[FEEDBACK] {msg}")
    if speak:
        _queue_speech(msg)
    return msg


def announce_navigation(message: str, speak: bool = True):
    """
    Speak and print navigation-specific prompts.
    """
    print(f"[NAV] {message}")
    if speak:
        _queue_speech(message)


def speak_text(text: str):
    """
    Enqueue arbitrary text to the TTS queue.
    """
    _queue_speech(text)


def wait_for_tts_idle(timeout: float | None = None) -> bool:
    """
    Block until the speech queue is empty or timeout expires.
    Returns True if idle was reached, False on timeout.
    """
    return _tts_idle.wait(timeout=timeout)

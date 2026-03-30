from __future__ import annotations

import os
import time
from typing import Any

from . import config
from .models import SensorStatus
from .queue_utils import put_latest


def audio_process_worker(audio_q: Any, status_q: Any, stop_event: Any) -> None:
    put_latest(status_q, SensorStatus("audio", True, "Audio process online.", time.time()))
    while not stop_event.is_set():
        try:
            msg = audio_q.get(timeout=0.2)
        except Exception:
            continue
        if not msg:
            continue

        try:
            if os.name != "nt":
                import subprocess

                if config.AUDIO_USE_APLAY_PIPE:
                    speak_proc = subprocess.Popen(
                        [
                            "espeak-ng",
                            "--stdout",
                            "-a",
                            str(config.AUDIO_ESPEAK_VOLUME),
                            "-s",
                            str(config.AUDIO_ESPEAK_RATE),
                            "-p",
                            str(config.AUDIO_ESPEAK_PITCH),
                            "-v",
                            config.AUDIO_ESPEAK_VOICE,
                            str(msg),
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                    )
                    subprocess.run(
                        [
                            "aplay",
                            "-D",
                            config.AUDIO_ALSA_DEVICE,
                        ],
                        stdin=speak_proc.stdout,
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    if speak_proc.stdout is not None:
                        speak_proc.stdout.close()
                    speak_proc.wait(timeout=5)
                else:
                    subprocess.run(
                        [
                            "espeak-ng",
                            "-a",
                            str(config.AUDIO_ESPEAK_VOLUME),
                            "-s",
                            str(config.AUDIO_ESPEAK_RATE),
                            "-p",
                            str(config.AUDIO_ESPEAK_PITCH),
                            "-v",
                            config.AUDIO_ESPEAK_VOICE,
                            str(msg),
                        ],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            else:
                print(f"[AUDIO] {msg}")
        except Exception:
            print(f"[AUDIO] {msg}")

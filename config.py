"""
Runtime configuration for AURA.

Every hardware component is optional at runtime. The orchestrator attempts to
start each module and degrades gracefully if a dependency/device is missing.
"""

# ----------------------------
# Core runtime
# ----------------------------
MAIN_LOOP_HZ = 10.0
USE_TTS = True
LOGGING_ENABLED = True
LOG_FILE_NAME = "aura_runtime_log.csv"
SENSOR_DEBUG_PRINTS = True
TOF_DEBUG_PRINT_INTERVAL_SEC = 0.5
IMU_DEBUG_PRINT_INTERVAL_SEC = 0.5
GPS_DEBUG_PRINT_INTERVAL_SEC = 1.0

# ----------------------------
# GPIO buttons (Pi only)
# ----------------------------
GPIO_BUTTONS_ENABLED = True
PAUSE_BUTTON_GPIO = 17
MODE_BUTTON_GPIO = 27
BUTTON_BOUNCE_MS = 250

# ----------------------------
# Camera worker
# ----------------------------
CAMERA_ENABLED = True
CAMERA_INDEX_CANDIDATES = [0, 1]
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 5
CAMERA_SLEEP_SEC = 0.10
DISPLAY_ENABLED = True

# ----------------------------
# Vision process (YOLO)
# ----------------------------
VISION_ENABLED = True
VISION_MODEL_PATH = "yolov8s-worldv2.pt"
VISION_IMGSZ = 192
VISION_CONFIDENCE = 0.35
VISION_TARGET_CLASSES = [
    "car", "truck", "bus", "motorcycle", "bicycle", "scooter",
    "traffic light", "stop sign", "crosswalk",
    "person", "wheelchair", "stroller",
    "bench", "fire hydrant", "trash can", "traffic cone",
    "pole", "tree", "fence",
    "stairs", "curb",
    "chair", "table", "door", "couch", "bed",
    "shopping cart", "suitcase", "backpack",
    "potted plant", "umbrella",
    "dog", "cat",
    "keyboard", "tv", "laptop", "phone", "bottle", "cup",
]

# ----------------------------
# Audio process
# ----------------------------
AUDIO_PROCESS_ENABLED = True
AUDIO_ESPEAK_RATE = 160
AUDIO_ESPEAK_VOICE = "en"
AUDIO_ESPEAK_VOLUME = 200
AUDIO_ESPEAK_PITCH = 35
AUDIO_USE_APLAY_PIPE = False
AUDIO_ALSA_DEVICE = "plughw:2,0"

# ----------------------------
# Navigation
# ----------------------------
NAVIGATION_ENABLED = True
NAVIGATION_DEFAULT_GOAL = "Kenneth Taylor Hall"
NAVIGATION_SPEECH_AT_START = True
NAVIGATION_SPEECH_TIMEOUT_SEC = 8.0
NAVIGATION_SPEECH_PHRASE_SEC = 6.0
NAVIGATION_SPEECH_AMBIENT_SEC = 1.0
NAVIGATION_SPEECH_ENERGY_THRESHOLD = 300
NAVIGATION_SPEECH_MIC_NAME_HINT = "USB"
NAVIGATION_SPEECH_PROMPT_LEAD_SEC = 1.2
NAVIGATION_GRAPHHOPPER_URL = "http://127.0.0.1:8989"
NAVIGATION_GRAPHHOPPER_PROFILE = "car"
NAVIGATION_ROUTE_STEP_TRIGGER_M = 15.0
NAVIGATION_ARRIVAL_RADIUS_M = 20.0
NAVIGATION_STARTUP_FOCUS_SEC = 12.0
NAVIGATION_ROUTE_RETRY_SEC = 5.0
NAVIGATION_WAITING_ANNOUNCE_SEC = 10.0
NAVIGATION_SUPPRESS_OTHER_ANNOUNCEMENTS_DURING_STARTUP = True
NAVIGATION_DESTINATION_ALIASES = {
    "kenneth taylor hall": "Kenneth Taylor Hall",
    "kth": "Kenneth Taylor Hall",
    "taylor hall": "Kenneth Taylor Hall",
    "engineering technology building": "Engineering Technology Building",
    "etb": "Engineering Technology Building",
    "student centre": "McMaster University Student Centre",
    "student center": "McMaster University Student Centre",
    "musc": "McMaster University Student Centre",
    "medical centre": "McMaster University Medical Centre",
    "medical center": "McMaster University Medical Centre",
    "hospital": "McMaster University Medical Centre",
    "mumc": "McMaster University Medical Centre",
    "thode": "H. G. Thode Library",
    "thode library": "H. G. Thode Library",
    "clarke": "E. T. Clarke Centre",
    "clarke centre": "E. T. Clarke Centre",
    "clarke center": "E. T. Clarke Centre",
}

# ----------------------------
# ToF worker (VL53L8CX)
# ----------------------------
TOF_ENABLED = True
DISTANCE_PROVIDER = "vl53l8cx"  # "vl53l8cx" or "mock"
TOF_LOOP_HZ = 15.0
TOF_CACHE_MS = 50
TOF_RESOLUTION = "8x8"
TOF_RANGING_HZ = 15
TOF_LPN_PIN = "D26"  # LPn wired to GPIO26 for logic-high enable/reset control
NEAR_THRESHOLD_M = 1.0
CENTER_MERGE_DELTA_M = 0.30

# ----------------------------
# IMU worker (MPU-6050)
# ----------------------------
IMU_ENABLED = True
IMU_MOCK_IF_UNAVAILABLE = False
IMU_LOOP_HZ = 20.0
IMU_TILT_ALERTS_ENABLED = True
IMU_TILT_AXIS_THRESHOLD = 2.0
IMU_TILT_STRONG_THRESHOLD = 4.0
IMU_TILT_PERSIST_SEC = 0.75
IMU_TILT_ANNOUNCE_COOLDOWN_SEC = 2.0

# ----------------------------
# GPS worker (NEO-8M)
# ----------------------------
GPS_ENABLED = True
GPS_MOCK_IF_UNAVAILABLE = False
GPS_LOOP_HZ = 1.0
GPS_SERIAL_PORT = "/dev/ttyAMA0"
GPS_BAUDRATE = 9600

# ----------------------------
# Wi-Fi position fallback
# ----------------------------
WIFI_POSITION_ENABLED = True
WIFI_POSITION_LOOP_HZ = 0.2
WIFI_POSITION_INTERFACE = "wlan0"
WIFI_POSITION_MIN_CONFIDENCE = 0.35
WIFI_DEBUG_PRINT_INTERVAL_SEC = 5.0
WIFI_POSITION_ANCHORS = {
    "MUSC-Anchor": {
        "ssid": "Mac-WIFI",
        "bssid": "a4:53:0e:7c:83:2d",
        "latitude": 43.26264,
        "longitude": -79.91715,
        "location_name": "McMaster University Student Centre",
    },
    "KTH-Anchor": {
        "ssid": "Mac-WIFI",
        "bssid": "a4:53:0e:7c:83:2d",
        "latitude": 43.26394,
        "longitude": -79.91917,
        "location_name": "Kenneth Taylor Hall",
    },
    "ETB-Anchor": {
        "ssid": "Mac-WIFI",
        "bssid": "a4:53:0e:7c:83:2d",
        "latitude": 43.25848,
        "longitude": -79.92012,
        "location_name": "Engineering Technology Building",
    },
}

# ----------------------------
# Announcement scheduler
# ----------------------------
ANNOUNCE_EMPTY_STREAK_REQUIRED = 3
ANNOUNCE_NORMAL_INTERVAL_SEC = 1.0
ANNOUNCE_RELAXED_INTERVAL_SEC = 1.5

# Ranking tiers from partner branch
PRIORITY_MAP = {
    "critical": {
        "car", "truck", "bus", "motorcycle", "bicycle", "scooter",
        "traffic light", "stop sign", "crosswalk",
    },
    "high": {
        "person", "wheelchair", "stroller", "pole", "stairs", "curb", "door",
    },
    "medium": {
        "bench", "fire hydrant", "trash can", "traffic cone",
        "tree", "fence", "chair", "table", "couch", "bed",
        "shopping cart", "suitcase", "potted plant",
    },
    "low": {
        "dog", "cat", "umbrella", "backpack", "phone", "keyboard", "tv", "laptop", "bottle", "cup",
    },
}

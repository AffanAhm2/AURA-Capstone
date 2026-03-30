# AURA - Assistive Unified Recognition and Awareness

AURA is a wearable assistive system for environmental awareness on Raspberry Pi.

## Current Software Architecture

The obstacle pipeline is modular so each subsystem can be developed and tested independently:

- `src/aura/providers.py`
  - Sensor providers that return normalized 8x8 distance frames (mm).
  - Includes `MockDistanceProvider` and `VL53L8CXProvider`.
- `src/aura/obstacle_service.py`
  - Hardware-agnostic obstacle detection and zone classification.
  - Produces stable `ObstacleReading` outputs.
- `src/aura/main.py`
  - Runtime loop, logging, speech feedback adapter, optional navigation demo.

## Why This Layout

- ToF code can run standalone.
- Webcam ML/object detection can be integrated as a separate producer/consumer.
- Navigation, haptics, and audio can subscribe to the same normalized reading format.

## Quick Start

1. Install dependencies:
   - `pip install -r requirements.txt`
2. Configure provider in `src/aura/config.py`:
   - Default is `DISTANCE_PROVIDER = "vl53l8cx"` for Raspberry Pi hardware
   - Set `DISTANCE_PROVIDER = "mock"` for local development
3. Run:
   - `python -m src.aura.main`

## Raspberry Pi 5 ToF Bring-up Notes

- Enable I2C (`raspi-config`).
- Confirm the sensor appears at `0x29`:
  - `i2cdetect -y 1`
- Use 3.3V logic-safe wiring and common ground.

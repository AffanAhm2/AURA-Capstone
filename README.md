# AURA – Assistive Unified Recognition and Awareness

AURA is a wearable assistive navigation system designed to enhance environmental awareness through real-time multi-sensor perception. Built on a Raspberry Pi, the system integrates depth sensing, computer vision, GPS-based navigation, and audio feedback to detect obstacles, identify objects, and guide users in real time.

---

## 🚀 Key Features

- Multi-sensor integration (ToF, Camera, GPS, IMU)
- Real-time obstacle detection and object recognition
- Sensor fusion and prioritization pipeline
- Audio feedback via text-to-speech (TTS)
- Navigation using GraphHopper routing
- WiFi-based positioning fallback for indoor environments
- Modular and scalable architecture

---

## 🧠 System Architecture

AURA is designed as a **modular, real-time processing system** using a hybrid concurrency model:

- **Multithreading** for sensor I/O (ToF, GPS, IMU)
- **Multiprocessing** for compute-intensive tasks (vision, audio)
- ~6–8 concurrent worker modules running in parallel

### Core Pipeline

### Components

- **Sensor Workers**
  - ToF (VL53L8CX) – depth sensing (8x8 grid)
  - Camera – object detection (ML inference)
  - GPS – positioning and navigation
  - IMU – motion and orientation

- **Processing**
  - Unified detection abstraction
  - Priority ranking algorithm (distance, confidence, spatial position, object weighting)
  - Scene filtering for stable outputs

- **Navigation**
  - GraphHopper routing server for real-time path computation
  - WiFi-based fallback for indoor positioning

- **Output**
  - Text-to-speech pipeline (I2S audio via MAX98357 amplifier)

---

## ⚙️ Software Architecture

The system is structured into modular components for independent development and testing:

- `src/aura/main.py`
  - Central runtime and system orchestration
  - Handles fusion, prioritization, and output pipeline

- `src/aura/providers.py`
  - Sensor providers with normalized outputs
  - Includes `VL53L8CXProvider` and `MockDistanceProvider`

- `src/aura/obstacle_service.py`
  - Hardware-agnostic obstacle detection and spatial classification

- `src/aura/vision_worker.py`
  - Camera-based object detection pipeline

- `src/aura/audio_worker.py`
  - Text-to-speech generation and audio output handling

- `src/aura/gps_worker.py`
  - GPS data acquisition and positioning

- `src/aura/navigation.py`
  - Integration with GraphHopper routing services

---

## 🔬 Technical Highlights

- Unified detection format for multi-sensor fusion
- Priority-based decision-making system
- Parallel execution using hybrid threading + multiprocessing
- Real-time performance with continuous sensor streams
- Context-aware filtering to prevent redundant feedback

---

## 🧪 Testing & Validation

- Controlled obstacle placement for ToF validation
- Real-time outdoor testing for navigation and object detection
- Indoor testing with WiFi positioning fallback
- End-to-end system validation with live audio feedback

---

## 🖥️ Hardware

- Raspberry Pi 5
- VL53L8CX Time-of-Flight Sensor (I2C)
- Camera Module (USB/CSI)
- NEO-8M GPS Module (UART)
- MPU6050 IMU (I2C)
- MAX98357 I2S Audio Amplifier + Speaker

---

## ⚡ Quick Start

1. Install dependencies:
2. Configure sensor provider in:

- Use hardware:
  ```
  DISTANCE_PROVIDER = "vl53l8cx"
  ```
- Use mock (development):
  ```
  DISTANCE_PROVIDER = "mock"
  ```

3. Run the system:

---

## 🧭 Future Improvements

- Improved sensor fusion with probabilistic models
- SLAM-based localization
- Enhanced object detection models
- Custom wearable enclosure and hardware optimization

---

## 📌 Summary

AURA demonstrates a complete real-time assistive system that combines perception, decision-making, and user interaction into a single wearable platform.

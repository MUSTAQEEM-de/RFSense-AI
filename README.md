# RFSense AI

Passive WiFi-Based Human Presence and Motion Detection System

## Overview

RFSense AI is a low-cost RF sensing prototype that uses existing WiFi signals to detect human movement without cameras or specialized radar hardware.

The system leverages an ESP32 to monitor WiFi signal strength (RSSI) fluctuations and a Python-based visualization engine to analyze and display movement activity in real time.

## Problem Statement

Traditional monitoring systems often rely on cameras, which may introduce privacy concerns and can be ineffective in low-light or visually obstructed environments.

This project explores the possibility of using ambient WiFi signals as a sensing medium for detecting human movement and environmental disturbances.

## How It Works

1. A WiFi hotspot continuously transmits wireless signals.
2. The ESP32 connects to the hotspot and measures RSSI values.
3. Human movement causes disturbances in signal propagation.
4. RSSI fluctuations are transmitted to a laptop over serial communication.
5. Python processes the signal data and performs frequency-domain analysis.
6. Results are displayed using:

   * Radar Visualization
   * Motion Spectrum (Spectrogram)
   * Movement Intensity Classification

## Technology Stack

### Hardware

* ESP32
* WiFi Hotspot
* Laptop

### Software

* Arduino IDE
* Python
* NumPy
* Matplotlib
* PySerial

## Features

* Real-time RSSI monitoring
* Motion detection using RF signal disturbances
* Radar-style visualization
* Spectrogram-based signal analysis
* Low-cost implementation
* Privacy-friendly sensing

## Current Capabilities

* Detects environmental movement
* Classifies movement intensity
* Generates real-time visual feedback

## Future Scope

The current prototype uses RSSI-based sensing.

Future development will focus on:

* Channel State Information (CSI)
* Human presence estimation
* Occupancy detection
* Movement tracking
* Through-obstacle sensing research
* AI-powered activity classification

## Project Structure

arduino/

* esp32_rssi_sensor.ino

python/

* rf_visualizer.py

screenshots/

* project images

docs/

* supporting documentation

## Authors

Mustaqeem

## License

MIT License

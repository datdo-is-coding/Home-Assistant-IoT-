# Home Assistant IoT Project Report

## Project Overview

This is a comprehensive IoT energy monitoring system that integrates hardware sensing, voice interaction, MQTT messaging, database storage, and web visualization for energy consumption monitoring. The system is built using ESP32-S3 microcontrollers, MQTT broker, PostgreSQL database, and containerized deployment with Docker Compose.

## System Architecture

### Hardware Component
- **ESP32-S3 Microcontroller**: Main IoT device with:
  - Sensor hardware for measuring electrical parameters (voltage, current, power, energy, power factor, frequency)
  - Voice assistant capabilities using ESP-SR (ESP-Speech Recognition) library
  - RGB LED indicators for system status visualization
  - I2S microphone and speaker for voice interaction
  - Voice control activation with "Hi ESP" command

### Software Components

#### 1. MQTT Server & Database
- **MQTT Broker**: Eclipse Mosquitto running in Docker container (port 1883)
- **Database**: PostgreSQL (port 5432) with Adminer web interface (port 8080)
- **Data Subscriber**: Python service that receives MQTT messages and writes to database

#### 2. Firmware
- **ESP32-S3 Firmware**: Built with PlatformIO using ESP-IDF framework
- **Voice Recognition**: Uses ESP-SR library for wake-word detection
- **Audio Processing**: I2S microphone and DAC for voice interaction
- **Sensor Data Collection**: Measures and reports electrical parameters

### Data Flow
1. **Sensor Data Collection**: ESP32-S3 measures electrical parameters
2. **MQTT Publishing**: Data is published to MQTT broker with topic `esp32/sensor/data`
3. **Data Processing**: Subscriber service receives MQTT messages
4. **Database Storage**: Processed data is saved to PostgreSQL database in `sensor_logs` table
5. **Data Visualization**: Adminer web interface allows viewing of real-time data

## Technical Details

### ESP32 Firmware
- **Platform**: ESP32-S3 N16R8 with ESP-IDF framework
- **Configuration**: Uses 4D Systems ESP32-S3 Gen4 R8N16 board
- **Memory**: 16MB flash with PSRAM support
- **Audio Features**:
  - Microphone: INMP441 MEMS Mic (I2S interface)
  - Speaker/DAC: MAX98357A I2S DAC/AMP
  - Voice recognition: ESP-SR wake-word detection
- **LED Control**: RMT-based WS2812 RGB LED driver on GPIO 48

### MQTT Configuration
- **Broker**: Eclipse Mosquitto
- **Port**: 1883 (standard MQTT port)
- **Topic**: `esp32/sensor/data`
- **Server IP**: 192.168.41.101

### Database Schema
- **Table**: `sensor_logs`
- **Columns**: 
  - `id`: Auto-incrementing primary key
  - `device_id`: Device identifier
  - `voltage`: NUMERIC(6,2) - Voltage in volts
  - `current`: NUMERIC(6,2) - Current in amperes
  - `power`: NUMERIC(8,2) - Power in watts
  - `energy`: NUMERIC(10,2) - Energy in watt-hours
  - `power_factor`: NUMERIC(4,2) - Power factor
  - `frequency`: NUMERIC(5,2) - Frequency in hertz
  - `created_at`: Timestamp with timezone

### Docker Compose Services
1. **iot_mosquitto**: MQTT broker service
2. **iot_postgres**: PostgreSQL database service
3. **iot_adminer**: Web database interface (port 8080)
4. **iot_subscriber**: MQTT data receiver and database writer

## Deployment & Operation

### System Operation
- **Start Server**: `docker compose up -d`
- **Check Status**: `docker compose ps`
- **View Logs**: `docker logs -f iot_subscriber`
- **Stop Server**: `docker compose down`

### Web Interface
- **Adminer Access**: http://localhost:8080
- **Database Login**:
  - System: PostgreSQL
  - Server: postgres
  - Username: iot_user
  - Password: iot_password
  - Database: iot_db

## Key Features

1. **Voice Control**: System can be activated with "Hi ESP" command
2. **Real-time Monitoring**: Live telemetry data via MQTT
3. **Web Dashboard**: Adminer interface for database access
4. **Containerized Deployment**: All services run in Docker containers
5. **Extensible Design**: Database schema supports additional columns for expanding functionality

## Configuration Parameters

### ESP32 Firmware Settings
- **MQTT Server IP**: 192.168.41.101
- **MQTT Port**: 1883
- **MQTT Topic**: `esp32/sensor/data`
- **Sensor Data Format**:
  ```json
  {
    "device_id": "ESP32_Energy_Monitor",
    "voltage": 225.40,
    "current": 1.35,
    "power": 298.20,
    "energy": 1925.10,
    "power_factor": 0.98,
    "frequency": 50.00
  }
  ```

## System Integration

This system is designed to integrate with the Home Assistant ecosystem, providing a complete IoT solution for energy monitoring with voice control capabilities. The modular design allows for easy expansion and integration with other smart home systems.

## Conclusion

The Home Assistant IoT project presents a robust, scalable solution for energy monitoring that combines hardware sensing, voice interaction, cloud messaging, and web visualization in a containerized environment. The system is well-documented and follows modern IoT architecture principles with clear separation of concerns between hardware, firmware, messaging, and data storage components.
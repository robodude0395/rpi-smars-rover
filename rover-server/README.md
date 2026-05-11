# SMARS Rover Server

Unified Python server for the SMARS Telepresence Rover. Runs on a Raspberry Pi 3B+ and provides motor control (SPI), MJPEG video streaming, and bidirectional audio over WebSockets.

## Prerequisites

- Raspberry Pi 3B+ (or any multicore Pi with WiFi)
- Python 3.9+
- SPI enabled via `raspi-config`
- USB webcam (V4L2 compatible)
- USB audio device or I2S microphone/speaker
- Arduino Pro Mini connected via SPI (CE0)

### Enable SPI

```bash
sudo raspi-config
# Navigate to: Interface Options → SPI → Enable
sudo reboot
```

## Installation

Clone the repository and run the install script:

```bash
cd rover-server
chmod +x install.sh
./install.sh
```

This installs system packages (`python3-opencv`, `python3-pyaudio`, `libasound2-dev`, `v4l-utils`, `alsa-utils`) and creates a virtual environment with all Python dependencies.

## Configuration

Default settings are defined in `config.py`. Key defaults:

| Setting | Default | Description |
|---------|---------|-------------|
| `server_port` | 8080 | HTTP/WebSocket port |
| `server_host` | 0.0.0.0 | Bind address |
| `spi_bus` | 0 | SPI bus number |
| `spi_device` | 0 | SPI device (CE0) |
| `spi_speed_hz` | 500000 | SPI clock speed |
| `video_resolution` | 320×240 | Capture resolution |
| `video_fps` | 10 | Target frame rate |
| `video_jpeg_quality` | 60 | JPEG compression (0-100) |
| `audio_sample_rate` | 16000 | Audio sample rate (Hz) |
| `audio_period_size` | 128 | ALSA playback period |

To change settings, edit `config.py` directly or use the REST API at runtime.

## Running the Server

```bash
source .venv/bin/activate
python main.py
```

The server starts on port 8080 and binds to all interfaces.

## API Endpoints

### HTTP

| Method | Path | Description |
|--------|------|-------------|
| GET | `/video_feed` | MJPEG video stream |
| GET | `/api/devices` | List detected video/audio devices |
| GET | `/api/config` | Get current configuration |
| POST | `/api/config` | Update configuration |
| GET | `/api/stream/status` | Stream state and uptime |
| POST | `/api/stream/start` | Start video + audio streams |
| POST | `/api/stream/stop` | Stop all streams |

### WebSocket Namespaces

| Namespace | Direction | Description |
|-----------|-----------|-------------|
| `/control` | Client → Server | Motor commands (JSON with left, right, seq) |
| `/audio_out` | Server → Client | Rover mic PCM audio (binary frames) |
| `/audio_in` | Client → Server | Client mic PCM audio (binary frames) |

## Hardware Connections

### SPI (Raspberry Pi → Arduino Pro Mini)

| Pi Pin | Arduino Pin | Signal |
|--------|-------------|--------|
| GPIO 10 (MOSI) | MOSI (11) | Data out |
| GPIO 9 (MISO) | MISO (12) | Data in |
| GPIO 11 (SCLK) | SCK (13) | Clock |
| GPIO 8 (CE0) | SS (10) | Chip select |
| GND | GND | Ground |

The Arduino Pro Mini runs existing firmware that receives 3-byte command packets: `[command_id, left_byte, right_byte]` using offset encoding (128 = stop).

## Troubleshooting

### SPI not available

```
ERROR: SPI device not available - motor control disabled
```

- Verify SPI is enabled: `ls /dev/spidev*` should show `/dev/spidev0.0`
- Enable via `sudo raspi-config` → Interface Options → SPI
- Reboot after enabling

### No camera detected

```
WARNING: Could not open video device 0
```

- Check USB webcam is connected: `v4l2-ctl --list-devices`
- Verify device permissions: `ls -la /dev/video*`
- Try a different device index in `config.py`

### No audio device

```
WARNING: No audio input device available
```

- List audio devices: `arecord -l`
- Check USB audio adapter is connected
- Verify ALSA configuration: `aplay -l` for output devices

### Port already in use

```
OSError: [Errno 98] Address already in use
```

- Kill existing process: `sudo lsof -i :8080` then `kill <PID>`
- Or change `server_port` in `config.py`

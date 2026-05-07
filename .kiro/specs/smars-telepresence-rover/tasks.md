# Implementation Plan: SMARS Telepresence Rover

## Overview

Implement a unified SMARS telepresence rover system by merging three existing standalone projects into a single cohesive platform. The server runs on a Raspberry Pi Zero W (Python, Flask-SocketIO) with SPI motor control, MJPEG video streaming, and bidirectional audio. The client is a Tauri desktop app (vanilla HTML/CSS/JS) providing WASD keyboard control, live video, and two-way audio.

## Tasks

- [ ] 1. Server Core — Project Structure and SPI Motor Control
  - [x] 1.1 Create server project structure and configuration module
    - Create `rover-server/` directory with `main.py`, `config.py`, `requirements.txt`
    - Implement `config.py` as a Python dataclass with fields: spi_bus, spi_device, spi_speed (500000), spi_mode (0), video_width (320), video_height (240), video_fps (10), jpeg_quality (60), audio_rate (16000), audio_channels (1), audio_chunk (512), audio_period_size (128), port (8080)
    - Include `requirements.txt` with pinned versions: flask, flask-socketio, python-socketio, gevent, gevent-websocket, pyalsaaudio, spidev, opencv-python, pyaudio
    - _Requirements: 13.1, 13.2_

  - [x] 1.2 Implement motor_controller.py with SPI interface
    - Create `RoverController` class wrapping spidev for SPI communication
    - Implement `send_command(left, right)` method that clamps values to -127..127, converts to offset encoding (value + 128), increments command_id (wrapping 0-255), and transmits 3-byte packet
    - Implement graceful fallback: if SPI unavailable at init, log error and set `enabled = False`
    - Implement `stop()` convenience method sending left=0, right=0
    - Implement SPI error handling with single retry before discard
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 14.4_

  - [ ]* 1.3 Write property test: Speed Encoding Round-Trip (Property 1)
    - **Property 1: Speed Encoding Round-Trip**
    - For any speed value v in -127..127, decoding(encoding(v)) == v where encoding(v) = v + 128 and decoding(b) = b - 128
    - **Validates: Requirements 1.1, 1.3**

  - [ ]* 1.4 Write property test: Command ID Wrapping (Property 2)
    - **Property 2: Command ID Wrapping**
    - After any sequence of N commands (N >= 0), command_id == N % 256
    - **Validates: Requirements 1.4**

  - [ ]* 1.5 Write property test: Motor Command Validation (Property 3)
    - **Property 3: Motor Command Validation**
    - For any integer inputs left and right, the encoded bytes are always in range 1..255 (since clamp to -127..127 then +128 gives 1..255)
    - **Validates: Requirements 1.1, 1.3**

  - [x] 1.6 Implement /control WebSocket namespace
    - Create Socket.IO namespace handler for `/control` in `main.py`
    - Validate incoming messages for required fields: type, left, right, seq
    - On valid motor command: call `RoverController.send_command()` and emit ack with matching seq
    - On invalid message: emit error event to sender
    - On client disconnect: send stop command via SPI
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 14.2_

- [x] 2. Checkpoint — Verify motor control
  - Ensure motor_controller.py and /control namespace work correctly
  - Run property tests for Properties 1, 2, 3
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. Video and Audio Streams
  - [x] 3.1 Implement video_stream.py with MJPEG generator
    - Create `VideoStream` class using OpenCV VideoCapture
    - Implement frame generator: capture → resize to configured resolution → JPEG encode at configured quality → yield as multipart frame
    - Implement frame pacing with inter-frame delay based on configured FPS
    - Handle missing camera gracefully (return None or raise descriptive error)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.2 Implement audio_capture.py (rover mic → client)
    - Create `AudioCapture` class using PyAudio in callback mode
    - Configure: 16kHz sample rate, mono, 16-bit signed format
    - Emit binary WebSocket frames of 512 bytes (256 samples) to /audio_out namespace
    - Handle missing audio device: log warning, disable capture
    - Implement start/stop lifecycle tied to client connections
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 3.3 Implement audio_playback.py (client → rover speaker)
    - Create `AudioPlayback` class using pyalsaaudio
    - Configure ALSA: PCM_PLAYBACK, PCM_FORMAT_S16_LE, mono, 16kHz, period size 128
    - Implement circular buffer holding at most 2 periods (256 samples)
    - On buffer overflow: discard oldest data, retain most recent 2 periods
    - Use separate receiver and player threads
    - Handle playback errors gracefully: log and continue receiving
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 14.5_

  - [ ]* 3.4 Write property test: Circular Buffer Capacity Invariant (Property 4)
    - **Property 4: Circular Buffer Capacity Invariant**
    - After any sequence of writes, buffer.size() <= max_capacity (2 * period_size)
    - **Validates: Requirements 5.3, 5.4**

  - [ ]* 3.5 Write property test: Audio Frame Chunking (Property 5)
    - **Property 5: Audio Frame Chunking**
    - For any input audio of length L bytes, the number of emitted chunks equals ceil(L / chunk_size) and concatenating all chunks reconstructs the original audio (possibly with zero-padding on last chunk)
    - **Validates: Requirements 4.3**

- [x] 4. Checkpoint — Verify streams independently
  - Ensure video streaming, audio capture, and audio playback work independently
  - Run property tests for Properties 4, 5
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Unified Server Integration
  - [x] 5.1 Integrate all components into main.py
    - Wire Flask-SocketIO app with all namespaces: /control, /audio_out, /audio_in
    - Register /video_feed HTTP route using video_stream generator
    - Initialize RoverController, VideoStream, AudioCapture, AudioPlayback on startup
    - Configure CORS to allow all origins
    - Bind to 0.0.0.0:8080 with threading async mode
    - _Requirements: 13.1, 13.2, 13.3_

  - [x] 5.2 Implement REST API endpoints
    - GET /api/devices — return detected video and audio devices as JSON
    - POST /api/stream/start — start video + audio with provided config
    - POST /api/stream/stop — stop all streams, release hardware
    - GET /api/stream/status — return state, uptime, active config
    - GET /api/config — return current server configuration
    - POST /api/config — update configuration (resolution, fps, audio settings)
    - Return HTTP 500 with "VIDEO_START_FAILED" if video device cannot be opened
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 5.3 Implement device_detector.py
    - Enumerate V4L2 video devices via v4l2-ctl subprocess: path, name, formats, resolutions, frame rates
    - Enumerate ALSA audio input devices via arecord subprocess: path, name, formats, sample rates, channels
    - Handle missing v4l2-ctl: return empty video list, log error
    - Handle missing arecord: return empty audio list, log error
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 5.4 Write property test: Configuration Round-Trip (Property 7)
    - **Property 7: Configuration Round-Trip**
    - For any valid configuration dict, serialize(deserialize(config)) == config (config dataclass to JSON and back preserves all fields)
    - **Validates: Requirements 6.5**

- [x] 6. Checkpoint — Verify unified server
  - Ensure all server components work concurrently (video + audio + motor)
  - Run property test for Property 7
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Desktop Client — Tauri Scaffold and UI
  - [x] 7.1 Create Tauri project scaffold
    - Initialize Tauri project in `rover-client/` with `npm init` and Tauri CLI
    - Configure `tauri.conf.json`: app name "SMARS Rover", window size 900x700, permissions for network access
    - Create `src/index.html` with main UI layout: video panel (70% height), control bar with motor controls, audio status, and connection panel
    - Create `src/css/styles.css` with layout and theming
    - Create `package.json` with Tauri CLI dependency
    - _Requirements: 16.1, 16.2, 16.4_

  - [x] 7.2 Implement app.js — connection management
    - Create connection UI: IP input field, Connect/Disconnect button, status indicator (green/red), latency display
    - On Connect: establish Socket.IO connections to /control, /audio_out, /audio_in namespaces at specified IP:8080
    - On Disconnect: close all WebSocket connections, stop MJPEG stream
    - Implement latency measurement using control channel ack round-trip time
    - Display connection state with visual indicators
    - _Requirements: 8.1, 8.2, 8.3, 8.5_

  - [x] 7.3 Implement reconnection with exponential backoff
    - On connection loss: show red indicator, attempt reconnection
    - Exponential backoff: start at 1s, double each attempt, cap at 30s
    - On successful reconnect: restore green indicator, resume normal operation
    - _Requirements: 8.4_

  - [ ]* 7.4 Write property test: Exponential Backoff Calculation (Property 8)
    - **Property 8: Exponential Backoff Calculation**
    - For attempt N (N >= 0), delay = min(initial_delay * 2^N, max_delay) and delay is always in range [initial_delay, max_delay]
    - **Validates: Requirements 8.4**

- [ ] 8. Desktop Client — Motor Control and Video
  - [x] 8.1 Implement motor.js — keyboard capture and command sending
    - Listen for keydown/keyup events for W, A, S, D, Space keys
    - Track key state (pressed/released) to handle multiple simultaneous keys
    - While any movement key held: send motor commands at 20Hz (50ms interval)
    - On all movement keys released: send single stop command (left=0, right=0)
    - Apply speed multiplier from slider (0-100%) to base value 127
    - Include incrementing sequence number in each command
    - Key mapping: W=forward, S=backward, A=turn left, D=turn right, Space=stop
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [ ]* 8.2 Write property test: Key State to Motor Command Mapping (Property 6)
    - **Property 6: Key State to Motor Command Mapping**
    - For any combination of key states {W, A, S, D}, the resulting (left, right) command values are always in range [-127, 127] and the mapping is deterministic
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**

  - [x] 8.3 Implement video.js — MJPEG display
    - Set `<img>` element src to `http://{rover_ip}:8080/video_feed` on connect
    - Clear src on disconnect
    - Show placeholder message when video unavailable or on error
    - _Requirements: 10.1, 10.2, 10.3_

- [ ] 9. Desktop Client — Bidirectional Audio
  - [x] 9.1 Implement audio_out.js — rover mic playback
    - Connect to /audio_out WebSocket namespace
    - Create Web Audio API AudioContext at 16kHz
    - Receive binary PCM frames, decode as 16-bit signed LE mono
    - Schedule buffer playback for gapless audio (target 50-100ms latency)
    - Provide speaker toggle control (enable/disable playback)
    - _Requirements: 11.1, 11.2, 11.5_

  - [x] 9.2 Implement audio_in.js — client mic capture and send
    - Capture local microphone via getUserMedia + AudioWorklet
    - Downsample from native sample rate (44.1/48kHz) to 16kHz
    - Send binary PCM frames (16-bit signed LE, mono) on /audio_in namespace
    - Provide mic toggle control (enable/disable transmission)
    - _Requirements: 11.3, 11.4, 11.5, 16.3_

  - [ ]* 9.3 Write property test: Audio Downsampling Length (Property 9)
    - **Property 9: Audio Downsampling Length**
    - For input of length N samples at source_rate, output length equals floor(N * target_rate / source_rate)
    - **Validates: Requirements 11.4**

- [ ] 10. Desktop Client — Settings Panel
  - [x] 10.1 Implement settings panel UI and logic
    - Create settings drawer/modal accessible via header settings button
    - Fetch available devices from GET /api/devices on open
    - Provide video resolution selector (populated from device capabilities)
    - Provide frame rate selector (5, 10, 15, 20, 30 fps)
    - Provide rover-side audio input device selector
    - On save: POST updated config to /api/config, restart affected streams via /api/stream/stop then /api/stream/start
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [x] 11. Checkpoint — Verify complete client
  - Ensure all client modules work together: connection, motor, video, audio in/out, settings
  - Run property tests for Properties 6, 8, 9
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Polish — Error Handling and Documentation
  - [x] 12.1 Add comprehensive error handling to server
    - Ensure SPI errors are logged and retried once before discard
    - Ensure audio playback errors are logged without crashing
    - Ensure video device unavailability returns HTTP 503 with descriptive message
    - Ensure all namespaces handle unexpected disconnects gracefully
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [x] 12.2 Add error handling and user feedback to client
    - Display user-friendly error messages for connection failures
    - Show descriptive status for each subsystem (motor, video, audio)
    - Handle WebSocket errors gracefully without crashing the app
    - _Requirements: 8.4, 14.2_

  - [x] 12.3 Create install script and documentation
    - Create `rover-server/install.sh` that installs system deps (python3-opencv, python3-pyaudio, libasound2-dev, v4l-utils, alsa-utils) and pip packages
    - Create `rover-server/README.md` with quickstart guide
    - Create `rover-client/README.md` with build and run instructions
    - _Requirements: 13.1_

- [x] 13. Final Checkpoint — Full system verification
  - Ensure all tests pass, ask the user if questions arise.
  - Verify server starts cleanly and all endpoints respond
  - Verify client builds successfully with Tauri

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at each phase boundary
- Property tests validate the 9 correctness properties defined in the design
- Server implementation uses Python (Flask-SocketIO, spidev, PyAudio, pyalsaaudio, OpenCV)
- Client implementation uses vanilla HTML/CSS/JavaScript with Tauri shell
- Arduino Pro Mini firmware requires no changes — existing firmware is production-ready

# Requirements Document

## Introduction

This document defines the requirements for the SMARS Telepresence Rover unified system. The system merges three existing standalone projects (motor control, webcam streaming, and mic audio streaming) into a single cohesive telepresence rover platform. The rover uses a Raspberry Pi Zero W as the main processor running a unified Python server, and an Arduino Pro Mini as the motor controller communicating via SPI. A Tauri-based desktop client provides remote control with live video, bidirectional audio, and motor control over WiFi.

## Glossary

- **Unified_Server**: The single Python process running on the Raspberry Pi Zero W that hosts all WebSocket namespaces, HTTP endpoints, and manages SPI communication, video capture, and audio I/O.
- **Desktop_Client**: The Tauri desktop application that connects to the Unified_Server and provides the user interface for controlling the rover.
- **Motor_Controller**: The Arduino Pro Mini firmware that receives SPI commands and drives the L293D motor driver with ramping and safety timeout.
- **SPI_Interface**: The Serial Peripheral Interface bus operating at 500kHz, SPI mode 0, connecting the Raspberry Pi Zero (master) to the Arduino Pro Mini (slave) via CE0.
- **Command_Packet**: A 3-byte SPI message consisting of [command_id, left_speed_byte, right_speed_byte] using offset encoding where 128 represents stop.
- **MJPEG_Stream**: Motion JPEG video delivered over HTTP multipart (multipart/x-mixed-replace) from the Unified_Server to the Desktop_Client.
- **Audio_Out_Channel**: The WebSocket namespace (/audio_out) carrying PCM audio from the rover microphone to the Desktop_Client speaker.
- **Audio_In_Channel**: The WebSocket namespace (/audio_in) carrying PCM audio from the Desktop_Client microphone to the rover speaker.
- **Control_Channel**: The WebSocket namespace (/control) carrying motor command messages from the Desktop_Client to the Unified_Server.
- **Offset_Encoding**: A byte encoding scheme where the value 128 represents zero/stop, values above 128 represent forward motion, and values below 128 represent reverse motion.
- **PCM_Audio**: Pulse Code Modulation audio in 16-bit signed little-endian format, mono channel, sampled at 16kHz.
- **ALSA**: Advanced Linux Sound Architecture, the audio subsystem used for playback on the Raspberry Pi.
- **V4L2**: Video4Linux2, the video capture interface used for webcam access on the Raspberry Pi.

## Requirements

### Requirement 1: SPI Motor Command Transmission

**User Story:** As a rover operator, I want motor commands sent from the server to the Arduino via SPI, so that I can control the rover's movement remotely.

#### Acceptance Criteria

1. WHEN a motor command is received on the Control_Channel, THE Unified_Server SHALL convert the left and right speed values from signed integers (-127 to 127) to Offset_Encoding bytes and transmit a 3-byte Command_Packet via the SPI_Interface within 10ms.
2. THE Unified_Server SHALL operate the SPI_Interface at 500kHz in SPI mode 0 on bus 0, device CE0.
3. WHEN a left or right speed value exceeds the range -127 to 127, THE Unified_Server SHALL clamp the value to the nearest boundary before encoding.
4. THE Unified_Server SHALL increment the command_id byte (wrapping at 255 to 0) for each transmitted Command_Packet.
5. IF the SPI_Interface is unavailable at startup, THEN THE Unified_Server SHALL log an error and continue operating with motor control disabled.

### Requirement 2: Motor Control WebSocket Namespace

**User Story:** As a rover operator, I want a dedicated WebSocket channel for motor commands, so that control messages are isolated from audio and video traffic.

#### Acceptance Criteria

1. THE Unified_Server SHALL expose a Socket.IO namespace at /control that accepts motor command messages.
2. WHEN a motor command message is received on the Control_Channel, THE Unified_Server SHALL validate that the message contains "type", "left", "right", and "seq" fields.
3. WHEN a valid motor command is received, THE Unified_Server SHALL respond with an acknowledgment message containing the same sequence number within 5ms of processing.
4. IF a motor command message is missing required fields or contains invalid types, THEN THE Unified_Server SHALL discard the message and emit an error event to the sender.
5. WHEN a client disconnects from the Control_Channel, THE Unified_Server SHALL send a stop command (left=0, right=0) to the Motor_Controller via SPI.

### Requirement 3: MJPEG Video Streaming

**User Story:** As a rover operator, I want to see live video from the rover's camera, so that I can navigate the rover visually.

#### Acceptance Criteria

1. THE Unified_Server SHALL expose an HTTP endpoint at /video_feed that streams MJPEG video using multipart/x-mixed-replace content type.
2. THE Unified_Server SHALL capture video frames from a V4L2 device, resize them to the configured resolution, and encode them as JPEG.
3. THE Unified_Server SHALL default to 320x240 resolution at 10 frames per second with JPEG quality 60.
4. WHEN no V4L2 video device is detected, THE Unified_Server SHALL return HTTP 503 on the /video_feed endpoint with a descriptive error message.
5. WHILE the video stream is active, THE Unified_Server SHALL maintain frame pacing according to the configured frame rate using inter-frame delays.

### Requirement 4: Audio Capture and Streaming (Rover to Client)

**User Story:** As a rover operator, I want to hear audio from the rover's microphone, so that I can be aware of the rover's environment.

#### Acceptance Criteria

1. THE Unified_Server SHALL expose a Socket.IO namespace at /audio_out that streams PCM_Audio from the rover microphone to connected clients.
2. THE Unified_Server SHALL capture audio using PyAudio in callback mode at 16kHz sample rate, mono, 16-bit signed format.
3. WHEN audio data is captured, THE Unified_Server SHALL emit binary WebSocket frames of 512 bytes (256 samples, 16ms of audio) to all connected clients on the Audio_Out_Channel.
4. IF no audio input device is detected, THEN THE Unified_Server SHALL log a warning and disable audio capture without affecting other system functions.
5. WHEN the last client disconnects from the Audio_Out_Channel, THE Unified_Server SHALL stop the audio capture stream to conserve CPU resources.

### Requirement 5: Audio Playback (Client to Rover)

**User Story:** As a rover operator, I want to speak through the rover's speaker, so that I can communicate with people near the rover.

#### Acceptance Criteria

1. THE Unified_Server SHALL expose a Socket.IO namespace at /audio_in that receives binary PCM_Audio frames from the Desktop_Client.
2. WHEN PCM_Audio data is received on the Audio_In_Channel, THE Unified_Server SHALL write the audio to the ALSA playback device configured for 16kHz, mono, 16-bit signed little-endian format with a period size of 128 samples.
3. THE Unified_Server SHALL maintain a circular buffer that retains at most 2 periods (256 samples) of audio data to prevent latency buildup.
4. WHEN the circular buffer overflows, THE Unified_Server SHALL discard the oldest audio data and retain the most recent 2 periods.
5. THE Unified_Server SHALL use separate receiver and player threads for audio playback to minimize latency between reception and output.

### Requirement 6: REST API for Configuration and Status

**User Story:** As a rover operator, I want to query and update the rover's configuration remotely, so that I can adjust video and audio settings without restarting the server.

#### Acceptance Criteria

1. THE Unified_Server SHALL expose a GET /api/devices endpoint that returns a JSON list of detected V4L2 video devices and ALSA audio devices with their capabilities.
2. THE Unified_Server SHALL expose a POST /api/stream/start endpoint that starts video and audio capture with the configuration provided in the request body.
3. THE Unified_Server SHALL expose a POST /api/stream/stop endpoint that stops all active video and audio streams and releases hardware resources.
4. THE Unified_Server SHALL expose a GET /api/stream/status endpoint that returns the current stream state, uptime in seconds, and active configuration.
5. THE Unified_Server SHALL expose GET and POST /api/config endpoints for reading and updating server configuration including resolution, frame rate, and audio settings.
6. IF a POST /api/stream/start request specifies a video device that cannot be opened, THEN THE Unified_Server SHALL return HTTP 500 with error code "VIDEO_START_FAILED" and a descriptive message.

### Requirement 7: Device Detection

**User Story:** As a rover operator, I want the server to detect available cameras and microphones, so that I can select the correct devices for streaming.

#### Acceptance Criteria

1. WHEN the /api/devices endpoint is called, THE Unified_Server SHALL enumerate V4L2 video devices using v4l2-ctl and return device path, name, and supported formats, resolutions, and frame rates.
2. WHEN the /api/devices endpoint is called, THE Unified_Server SHALL enumerate ALSA audio input devices using arecord and return device path, name, and supported formats, sample rates, and channels.
3. IF v4l2-ctl is not installed on the system, THEN THE Unified_Server SHALL return an empty video device list and log an error indicating the missing dependency.
4. IF arecord is not installed on the system, THEN THE Unified_Server SHALL return an empty audio device list and log an error indicating the missing dependency.

### Requirement 8: Desktop Client Connection Management

**User Story:** As a rover operator, I want to connect to the rover by entering its IP address, so that I can establish control from my desktop.

#### Acceptance Criteria

1. THE Desktop_Client SHALL provide a text input field for the rover IP address and a Connect button.
2. WHEN the user clicks Connect, THE Desktop_Client SHALL establish WebSocket connections to the /control, /audio_out, and /audio_in namespaces on the specified IP at port 8080.
3. WHILE connected, THE Desktop_Client SHALL display a green status indicator and the measured round-trip latency in milliseconds.
4. WHEN a WebSocket connection is lost, THE Desktop_Client SHALL display a red status indicator and attempt reconnection using exponential backoff starting at 1 second with a maximum interval of 30 seconds.
5. WHEN the user clicks Disconnect, THE Desktop_Client SHALL close all WebSocket connections and stop the MJPEG video stream.

### Requirement 9: Desktop Client Motor Control

**User Story:** As a rover operator, I want to drive the rover using keyboard keys, so that I can navigate intuitively.

#### Acceptance Criteria

1. WHILE the W key is held, THE Desktop_Client SHALL send motor commands with left=speed and right=speed (forward) at 20Hz on the Control_Channel.
2. WHILE the S key is held, THE Desktop_Client SHALL send motor commands with left=-speed and right=-speed (backward) at 20Hz on the Control_Channel.
3. WHILE the A key is held, THE Desktop_Client SHALL send motor commands with left=-speed and right=speed (turn left) at 20Hz on the Control_Channel.
4. WHILE the D key is held, THE Desktop_Client SHALL send motor commands with left=speed and right=-speed (turn right) at 20Hz on the Control_Channel.
5. WHEN a movement key is released and no other movement key is held, THE Desktop_Client SHALL send a single stop command (left=0, right=0) on the Control_Channel.
6. THE Desktop_Client SHALL provide a speed slider (0-100%) that scales the base speed value (127) applied to motor commands.
7. THE Desktop_Client SHALL include an incrementing sequence number in each motor command message for latency measurement.

### Requirement 10: Desktop Client Video Display

**User Story:** As a rover operator, I want to see the rover's camera feed in the application window, so that I can see where the rover is going.

#### Acceptance Criteria

1. WHEN connected to the rover, THE Desktop_Client SHALL display the MJPEG_Stream from http://{rover_ip}:8080/video_feed in the primary display area occupying approximately 70% of the window height.
2. WHEN the video stream fails to load or disconnects, THE Desktop_Client SHALL display a placeholder message indicating the video feed is unavailable.
3. THE Desktop_Client SHALL render the video feed without additional client-side decoding by using an HTML img element with the MJPEG stream URL as its source.

### Requirement 11: Desktop Client Audio (Bidirectional)

**User Story:** As a rover operator, I want to hear the rover's environment and speak through the rover, so that I can have two-way communication.

#### Acceptance Criteria

1. WHEN connected to the Audio_Out_Channel, THE Desktop_Client SHALL play received PCM_Audio frames using the Web Audio API with an AudioContext configured at 16kHz sample rate.
2. THE Desktop_Client SHALL schedule audio buffer playback to achieve gapless audio output with a target latency of 50-100ms.
3. WHEN the user enables microphone transmission, THE Desktop_Client SHALL capture audio from the local microphone using getUserMedia and an AudioWorklet.
4. THE Desktop_Client SHALL downsample captured audio from the native sample rate to 16kHz before sending binary PCM frames on the Audio_In_Channel.
5. THE Desktop_Client SHALL provide toggle controls for enabling and disabling both microphone transmission and speaker playback independently.

### Requirement 12: Desktop Client Settings Panel

**User Story:** As a rover operator, I want to adjust video and audio settings from the client, so that I can optimize the experience for my network conditions.

#### Acceptance Criteria

1. THE Desktop_Client SHALL provide a settings panel accessible via a settings button in the application header.
2. THE Desktop_Client SHALL allow selection of video resolution from the resolutions reported by the /api/devices endpoint.
3. THE Desktop_Client SHALL allow selection of frame rate (5, 10, 15, 20, 30 fps).
4. THE Desktop_Client SHALL allow selection of the rover-side audio input device from devices reported by the /api/devices endpoint.
5. WHEN settings are changed, THE Desktop_Client SHALL send the updated configuration to the Unified_Server via POST /api/config and restart affected streams.

### Requirement 13: Server Single-Process Architecture

**User Story:** As a system maintainer, I want the server to run as a single Python process, so that deployment and debugging on the Pi Zero are straightforward.

#### Acceptance Criteria

1. THE Unified_Server SHALL run all functionality (WebSocket namespaces, HTTP endpoints, SPI communication, video capture, audio capture, and audio playback) within a single Python process using Flask-SocketIO with threading async mode.
2. THE Unified_Server SHALL listen on port 8080 and bind to all network interfaces (0.0.0.0).
3. THE Unified_Server SHALL allow cross-origin requests from all origins to support Desktop_Client connections from any host.
4. WHILE running on a Raspberry Pi Zero W, THE Unified_Server SHALL consume no more than 50% total CPU during concurrent video streaming, audio streaming, and motor control operation.

### Requirement 14: Safety and Error Handling

**User Story:** As a rover operator, I want the rover to stop safely if communication is lost, so that the rover does not drive uncontrolled.

#### Acceptance Criteria

1. WHEN no motor command is received for 1000ms, THE Motor_Controller SHALL set both motor target speeds to zero.
2. WHEN a client disconnects from the Control_Channel unexpectedly, THE Unified_Server SHALL transmit a stop Command_Packet to the Motor_Controller within 100ms.
3. IF the Unified_Server process terminates, THEN THE Motor_Controller SHALL stop both motors within 1000ms due to the safety timeout.
4. IF an error occurs during SPI transmission, THEN THE Unified_Server SHALL log the error and retry the transmission once before discarding the command.
5. IF an error occurs during audio playback, THEN THE Unified_Server SHALL log the error and continue receiving audio data without crashing.

### Requirement 15: Latency Performance

**User Story:** As a rover operator, I want responsive controls and low-delay audio, so that operating the rover feels immediate and natural.

#### Acceptance Criteria

1. WHEN a motor command is sent from the Desktop_Client, THE system SHALL deliver the corresponding SPI transmission to the Motor_Controller within 50ms end-to-end.
2. WHEN audio is captured by the rover microphone, THE system SHALL deliver the audio to the Desktop_Client speaker within 100ms end-to-end.
3. WHEN audio is captured by the Desktop_Client microphone, THE system SHALL deliver the audio to the rover speaker within 100ms end-to-end.
4. WHEN a video frame is captured by the rover camera, THE system SHALL deliver the rendered frame to the Desktop_Client display within 200ms end-to-end.

### Requirement 16: Tauri Desktop Application Shell

**User Story:** As a rover operator, I want a lightweight native desktop application, so that I can control the rover without browser permission issues and with minimal resource usage.

#### Acceptance Criteria

1. THE Desktop_Client SHALL be built using the Tauri framework with a vanilla HTML/CSS/JavaScript frontend.
2. THE Desktop_Client SHALL produce a standalone binary of less than 20MB for macOS, Windows, and Linux platforms.
3. THE Desktop_Client SHALL provide native microphone access without requiring HTTPS or browser security prompts.
4. THE Desktop_Client SHALL support development mode with hot-reload via the Tauri CLI for rapid frontend iteration.

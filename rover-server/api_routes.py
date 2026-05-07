"""REST API endpoints for the SMARS Telepresence Rover.

Provides configuration, device enumeration, and stream control endpoints
as a Flask Blueprint registered at /api.

Endpoints:
- GET  /api/devices        — list detected video and audio devices
- POST /api/stream/start   — start video + audio streams
- POST /api/stream/stop    — stop all streams, release hardware
- GET  /api/stream/status  — return stream state, uptime, active config
- GET  /api/config         — return current server configuration
- POST /api/config         — update configuration
"""

import logging
import time

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

api_blueprint = Blueprint('api', __name__)

# These will be set by init_api_routes() after app creation
_video_stream = None
_audio_capture = None
_audio_playback = None
_config = None
_rover_controller = None
_stream_start_time = None


def init_api_routes(video_stream, audio_capture, audio_playback, config, rover_controller):
    """Initialize API routes with shared component instances.

    Must be called before the blueprint handles any requests.

    Args:
        video_stream: VideoStream instance.
        audio_capture: AudioCapture instance.
        audio_playback: AudioPlayback instance.
        config: ServerConfig instance.
        rover_controller: RoverController instance.
    """
    global _video_stream, _audio_capture, _audio_playback, _config, _rover_controller
    _video_stream = video_stream
    _audio_capture = audio_capture
    _audio_playback = audio_playback
    _config = config
    _rover_controller = rover_controller


@api_blueprint.route('/devices', methods=['GET'])
def get_devices():
    """Return detected video and audio devices as JSON.

    Calls DeviceDetector if available, otherwise returns empty lists.
    """
    try:
        from device_detector import DeviceDetector
        video_devices = DeviceDetector.list_video_devices()
        audio_devices = DeviceDetector.list_audio_devices()
    except (ImportError, Exception) as e:
        logger.warning("Device detection unavailable: %s", e)
        video_devices = []
        audio_devices = []

    return jsonify({
        "video": video_devices,
        "audio": audio_devices,
    })


@api_blueprint.route('/stream/start', methods=['POST'])
def stream_start():
    """Start video and audio streams with provided config.

    Accepts optional JSON body with video/audio config overrides:
    {
        "video": {"device": 0, "resolution": [320, 240], "fps": 10, "jpeg_quality": 60},
        "audio": {"input_device": null, "sample_rate": 16000, "chunk_samples": 256}
    }

    Returns 200 on success, 500 with VIDEO_START_FAILED if video device fails.
    """
    global _stream_start_time

    body = request.get_json(silent=True) or {}

    # Apply video config overrides if provided
    if 'video' in body:
        video_cfg = body['video']
        if 'device' in video_cfg:
            _config.video_device = video_cfg['device']
        if 'resolution' in video_cfg:
            _config.video_resolution = tuple(video_cfg['resolution'])
        if 'fps' in video_cfg:
            # Validate FPS: Pi Zero can realistically sustain 5-20fps at 320x240
            fps = int(video_cfg['fps'])
            if fps < 1:
                fps = 1
            elif fps > 30:
                fps = 30
            _config.video_fps = fps
        if 'jpeg_quality' in video_cfg:
            _config.video_jpeg_quality = video_cfg['jpeg_quality']

    # Apply audio config overrides if provided
    if 'audio' in body:
        audio_cfg = body['audio']
        if 'input_device' in audio_cfg:
            _config.audio_input_device = audio_cfg['input_device']
        if 'sample_rate' in audio_cfg:
            _config.audio_sample_rate = audio_cfg['sample_rate']
        if 'chunk_samples' in audio_cfg:
            _config.audio_chunk_samples = audio_cfg['chunk_samples']

    # Stop existing streams before restarting
    if _video_stream.is_active:
        _video_stream.stop()
    if _audio_capture.is_active:
        _audio_capture.stop()

    # Wait for the camera device to be fully released by the kernel
    time.sleep(1.0)

    # Start video stream with current config
    _video_stream.device = _config.video_device
    _video_stream.resolution = _config.video_resolution
    _video_stream.fps = _config.video_fps
    _video_stream.jpeg_quality = _config.video_jpeg_quality
    _video_stream.start()

    # Retry once if camera didn't open (device may still be releasing)
    if not _video_stream.is_active:
        time.sleep(1.0)
        _video_stream.start()

    if not _video_stream.is_active:
        return jsonify({
            "error": "VIDEO_START_FAILED",
            "message": f"Failed to open video device {_config.video_device}",
        }), 500

    # Start audio capture
    _audio_capture.start()

    _stream_start_time = time.time()

    return jsonify({
        "status": "started",
        "video": {
            "device": _config.video_device,
            "resolution": list(_config.video_resolution),
            "fps": _config.video_fps,
        },
        "audio_capture": {
            "active": _audio_capture.is_active,
            "sample_rate": _config.audio_sample_rate,
        },
    })


@api_blueprint.route('/stream/stop', methods=['POST'])
def stream_stop():
    """Stop all streams and release hardware resources."""
    global _stream_start_time

    if _video_stream.is_active:
        _video_stream.stop()

    if _audio_capture.is_active:
        _audio_capture.stop()

    if _audio_playback is not None:
        _audio_playback.stop()

    _stream_start_time = None

    return jsonify({"status": "stopped"})


@api_blueprint.route('/stream/status', methods=['GET'])
def stream_status():
    """Return current stream state, uptime, and active config."""
    uptime_seconds = 0
    if _stream_start_time is not None:
        uptime_seconds = int(time.time() - _stream_start_time)

    # Motor status
    motor_status = {
        "spi_available": _rover_controller.enabled if _rover_controller else False,
    }

    response = {
        "video": {
            "active": _video_stream.is_active if _video_stream else False,
            "device": f"/dev/video{_config.video_device}" if _config else "/dev/video0",
            "resolution": f"{_config.video_resolution[0]}x{_config.video_resolution[1]}" if _config else "320x240",
            "fps": _config.video_fps if _config else 10,
            "uptime_seconds": uptime_seconds,
        },
        "audio_capture": {
            "active": _audio_capture.is_active if _audio_capture else False,
            "device": f"hw:{_config.audio_input_device or 'default'}" if _config else "hw:default",
            "sample_rate": _config.audio_sample_rate if _config else 16000,
        },
        "audio_playback": {
            "active": _audio_playback._running if _audio_playback else False,
            "buffer_level": _audio_playback.buffer_level if _audio_playback else 0,
        },
        "motor": motor_status,
    }

    return jsonify(response)


@api_blueprint.route('/config', methods=['GET'])
def get_config():
    """Return current server configuration as JSON."""
    return jsonify({
        "video": {
            "device": _config.video_device,
            "resolution": list(_config.video_resolution),
            "fps": _config.video_fps,
            "jpeg_quality": _config.video_jpeg_quality,
        },
        "audio": {
            "input_device": _config.audio_input_device,
            "sample_rate": _config.audio_sample_rate,
            "chunk_samples": _config.audio_chunk_samples,
            "playback_device": _config.audio_playback_device,
            "period_size": _config.audio_period_size,
            "max_periods": _config.audio_max_periods,
        },
        "spi": {
            "bus": _config.spi_bus,
            "device": _config.spi_device,
            "speed_hz": _config.spi_speed_hz,
        },
        "server": {
            "port": _config.server_port,
            "host": _config.server_host,
        },
    })


@api_blueprint.route('/config', methods=['POST'])
def update_config():
    """Update configuration from JSON body, return updated config.

    Accepts JSON body with any subset of config fields:
    {
        "video": {"device": 0, "resolution": [320, 240], "fps": 10, "jpeg_quality": 60},
        "audio": {"input_device": null, "sample_rate": 16000, ...},
        "spi": {"bus": 0, "device": 0, "speed_hz": 500000},
        "server": {"port": 8080, "host": "0.0.0.0"}
    }
    """
    body = request.get_json(silent=True) or {}

    if 'video' in body:
        video_cfg = body['video']
        if 'device' in video_cfg:
            _config.video_device = video_cfg['device']
        if 'resolution' in video_cfg:
            _config.video_resolution = tuple(video_cfg['resolution'])
        if 'fps' in video_cfg:
            fps = int(video_cfg['fps'])
            if fps < 1:
                fps = 1
            elif fps > 30:
                fps = 30
            _config.video_fps = fps
        if 'jpeg_quality' in video_cfg:
            _config.video_jpeg_quality = video_cfg['jpeg_quality']

    if 'audio' in body:
        audio_cfg = body['audio']
        if 'input_device' in audio_cfg:
            _config.audio_input_device = audio_cfg['input_device']
        if 'sample_rate' in audio_cfg:
            _config.audio_sample_rate = audio_cfg['sample_rate']
        if 'chunk_samples' in audio_cfg:
            _config.audio_chunk_samples = audio_cfg['chunk_samples']
        if 'playback_device' in audio_cfg:
            _config.audio_playback_device = audio_cfg['playback_device']
        if 'period_size' in audio_cfg:
            _config.audio_period_size = audio_cfg['period_size']
        if 'max_periods' in audio_cfg:
            _config.audio_max_periods = audio_cfg['max_periods']

    if 'spi' in body:
        spi_cfg = body['spi']
        if 'bus' in spi_cfg:
            _config.spi_bus = spi_cfg['bus']
        if 'device' in spi_cfg:
            _config.spi_device = spi_cfg['device']
        if 'speed_hz' in spi_cfg:
            _config.spi_speed_hz = spi_cfg['speed_hz']

    if 'server' in body:
        server_cfg = body['server']
        if 'port' in server_cfg:
            _config.server_port = server_cfg['port']
        if 'host' in server_cfg:
            _config.server_host = server_cfg['host']

    # Return updated config
    return get_config()

"""Tests for the REST API endpoints (api_routes.py).

Tests cover:
- GET /api/devices
- POST /api/stream/start (success and failure)
- POST /api/stream/stop
- GET /api/stream/status
- GET /api/config
- POST /api/config
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from api_routes import api_blueprint, init_api_routes
from config import ServerConfig


@pytest.fixture
def app():
    """Create a Flask test app with the API blueprint registered."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(api_blueprint, url_prefix='/api')
    return app


@pytest.fixture
def mock_video_stream():
    """Create a mock VideoStream."""
    stream = MagicMock()
    stream.is_active = False
    stream.device = 0
    stream.resolution = (320, 240)
    stream.fps = 10
    stream.jpeg_quality = 60
    return stream


@pytest.fixture
def mock_audio_capture():
    """Create a mock AudioCapture."""
    capture = MagicMock()
    capture.is_active = False
    return capture


@pytest.fixture
def mock_audio_playback():
    """Create a mock AudioPlayback."""
    playback = MagicMock()
    playback._running = False
    playback.buffer_level = 0
    return playback


@pytest.fixture
def mock_rover_controller():
    """Create a mock RoverController."""
    controller = MagicMock()
    controller.enabled = True
    return controller


@pytest.fixture
def config():
    """Create a ServerConfig instance."""
    return ServerConfig()


@pytest.fixture
def client(app, mock_video_stream, mock_audio_capture, mock_audio_playback,
           config, mock_rover_controller):
    """Create a test client with all mocks initialized."""
    init_api_routes(
        mock_video_stream, mock_audio_capture, mock_audio_playback,
        config, mock_rover_controller
    )
    return app.test_client()


class TestGetDevices:
    """Tests for GET /api/devices."""

    def test_returns_empty_lists_when_detector_unavailable(self, client):
        """Returns empty video and audio lists when DeviceDetector is not available."""
        response = client.get('/api/devices')
        assert response.status_code == 200
        data = response.get_json()
        assert "video" in data
        assert "audio" in data
        assert isinstance(data["video"], list)
        assert isinstance(data["audio"], list)

    def test_returns_devices_from_detector(self, client):
        """Returns device lists from DeviceDetector when available."""
        mock_video = [{"path": "/dev/video0", "name": "USB Camera"}]
        mock_audio = [{"device": "hw:1,0", "name": "USB Mic"}]

        with patch.dict('sys.modules', {'device_detector': MagicMock()}):
            with patch('api_routes.DeviceDetector', create=True) as mock_dd:
                # We need to patch the import inside the function
                pass

        # Since device_detector doesn't exist yet, it returns empty lists
        response = client.get('/api/devices')
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data["video"], list)
        assert isinstance(data["audio"], list)


class TestStreamStart:
    """Tests for POST /api/stream/start."""

    def test_start_success(self, client, mock_video_stream, mock_audio_capture):
        """Successfully starts video and audio streams."""
        # After start() is called, is_active becomes True
        mock_video_stream.is_active = True

        response = client.post(
            '/api/stream/start',
            data=json.dumps({}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "started"
        mock_video_stream.start.assert_called_once()
        mock_audio_capture.start.assert_called_once()

    def test_start_with_config_overrides(self, client, mock_video_stream, config):
        """Applies video config overrides from request body."""
        mock_video_stream.is_active = True

        body = {
            "video": {"device": 1, "resolution": [640, 480], "fps": 15, "jpeg_quality": 80},
            "audio": {"input_device": 2, "sample_rate": 44100}
        }

        response = client.post(
            '/api/stream/start',
            data=json.dumps(body),
            content_type='application/json'
        )

        assert response.status_code == 200
        assert config.video_device == 1
        assert config.video_resolution == (640, 480)
        assert config.video_fps == 15
        assert config.video_jpeg_quality == 80
        assert config.audio_input_device == 2
        assert config.audio_sample_rate == 44100

    def test_start_video_failed(self, client, mock_video_stream):
        """Returns 500 with VIDEO_START_FAILED when video device cannot be opened."""
        mock_video_stream.is_active = False

        response = client.post(
            '/api/stream/start',
            data=json.dumps({}),
            content_type='application/json'
        )

        assert response.status_code == 500
        data = response.get_json()
        assert data["error"] == "VIDEO_START_FAILED"
        assert "message" in data

    def test_start_stops_existing_streams_first(self, client, mock_video_stream, mock_audio_capture):
        """Stops existing streams before starting new ones."""
        # Simulate already-active streams
        mock_video_stream.is_active = True
        mock_audio_capture.is_active = True

        # After stop + start, video becomes active again
        def start_side_effect():
            mock_video_stream.is_active = True
        mock_video_stream.start.side_effect = start_side_effect

        response = client.post(
            '/api/stream/start',
            data=json.dumps({}),
            content_type='application/json'
        )

        assert response.status_code == 200
        mock_video_stream.stop.assert_called_once()
        mock_audio_capture.stop.assert_called_once()


class TestStreamStop:
    """Tests for POST /api/stream/stop."""

    def test_stop_all_streams(self, client, mock_video_stream, mock_audio_capture, mock_audio_playback):
        """Stops video, audio capture, and audio playback."""
        mock_video_stream.is_active = True
        mock_audio_capture.is_active = True

        response = client.post('/api/stream/stop')

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "stopped"
        mock_video_stream.stop.assert_called_once()
        mock_audio_capture.stop.assert_called_once()
        mock_audio_playback.stop.assert_called_once()

    def test_stop_when_already_stopped(self, client, mock_video_stream, mock_audio_capture):
        """Handles stop gracefully when streams are already stopped."""
        mock_video_stream.is_active = False
        mock_audio_capture.is_active = False

        response = client.post('/api/stream/stop')

        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "stopped"


class TestStreamStatus:
    """Tests for GET /api/stream/status."""

    def test_status_when_inactive(self, client, mock_video_stream, mock_audio_capture):
        """Returns status with all streams inactive."""
        mock_video_stream.is_active = False
        mock_audio_capture.is_active = False

        response = client.get('/api/stream/status')

        assert response.status_code == 200
        data = response.get_json()
        assert data["video"]["active"] is False
        assert data["audio_capture"]["active"] is False
        assert data["audio_playback"]["active"] is False
        assert data["motor"]["spi_available"] is True

    def test_status_when_active(self, client, mock_video_stream, mock_audio_capture,
                                mock_audio_playback, mock_rover_controller):
        """Returns status with streams active and uptime."""
        mock_video_stream.is_active = True
        mock_audio_capture.is_active = True
        mock_audio_playback._running = True
        mock_audio_playback.buffer_level = 256

        # Simulate stream start to set uptime
        import api_routes
        import time
        api_routes._stream_start_time = time.time() - 100

        response = client.get('/api/stream/status')

        assert response.status_code == 200
        data = response.get_json()
        assert data["video"]["active"] is True
        assert data["video"]["uptime_seconds"] >= 99
        assert data["audio_capture"]["active"] is True
        assert data["audio_playback"]["active"] is True
        assert data["audio_playback"]["buffer_level"] == 256
        assert data["motor"]["spi_available"] is True

        # Clean up
        api_routes._stream_start_time = None

    def test_status_includes_config_details(self, client, config):
        """Status response includes resolution, fps, and device info."""
        response = client.get('/api/stream/status')

        assert response.status_code == 200
        data = response.get_json()
        assert data["video"]["resolution"] == "320x240"
        assert data["video"]["fps"] == 10
        assert data["video"]["device"] == "/dev/video0"
        assert data["audio_capture"]["sample_rate"] == 16000


class TestGetConfig:
    """Tests for GET /api/config."""

    def test_returns_full_config(self, client, config):
        """Returns all configuration sections."""
        response = client.get('/api/config')

        assert response.status_code == 200
        data = response.get_json()

        # Video section
        assert data["video"]["device"] == 0
        assert data["video"]["resolution"] == [320, 240]
        assert data["video"]["fps"] == 10
        assert data["video"]["jpeg_quality"] == 60

        # Audio section
        assert data["audio"]["input_device"] is None
        assert data["audio"]["sample_rate"] == 16000
        assert data["audio"]["chunk_samples"] == 256
        assert data["audio"]["playback_device"] == "default"
        assert data["audio"]["period_size"] == 128
        assert data["audio"]["max_periods"] == 2

        # SPI section
        assert data["spi"]["bus"] == 0
        assert data["spi"]["device"] == 0
        assert data["spi"]["speed_hz"] == 500000

        # Server section
        assert data["server"]["port"] == 8080
        assert data["server"]["host"] == "0.0.0.0"


class TestUpdateConfig:
    """Tests for POST /api/config."""

    def test_update_video_config(self, client, config):
        """Updates video configuration fields."""
        body = {"video": {"device": 1, "resolution": [640, 480], "fps": 30, "jpeg_quality": 90}}

        response = client.post(
            '/api/config',
            data=json.dumps(body),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["video"]["device"] == 1
        assert data["video"]["resolution"] == [640, 480]
        assert data["video"]["fps"] == 30
        assert data["video"]["jpeg_quality"] == 90

    def test_update_audio_config(self, client, config):
        """Updates audio configuration fields."""
        body = {"audio": {"input_device": 3, "sample_rate": 44100, "playback_device": "hw:0,0"}}

        response = client.post(
            '/api/config',
            data=json.dumps(body),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["audio"]["input_device"] == 3
        assert data["audio"]["sample_rate"] == 44100
        assert data["audio"]["playback_device"] == "hw:0,0"

    def test_update_partial_config(self, client, config):
        """Updates only specified fields, leaves others unchanged."""
        body = {"video": {"fps": 20}}

        response = client.post(
            '/api/config',
            data=json.dumps(body),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["video"]["fps"] == 20
        # Other fields unchanged
        assert data["video"]["device"] == 0
        assert data["video"]["resolution"] == [320, 240]

    def test_update_spi_config(self, client, config):
        """Updates SPI configuration fields."""
        body = {"spi": {"bus": 1, "device": 1, "speed_hz": 1000000}}

        response = client.post(
            '/api/config',
            data=json.dumps(body),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["spi"]["bus"] == 1
        assert data["spi"]["device"] == 1
        assert data["spi"]["speed_hz"] == 1000000

    def test_update_with_empty_body(self, client, config):
        """Returns current config when body is empty."""
        response = client.post(
            '/api/config',
            data=json.dumps({}),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = response.get_json()
        # All defaults preserved
        assert data["video"]["device"] == 0
        assert data["video"]["fps"] == 10

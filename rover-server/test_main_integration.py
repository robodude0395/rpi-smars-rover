"""Integration tests for main.py — verifying all components are wired together."""

import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock hardware modules before importing main
mock_spidev = MagicMock()
sys.modules['spidev'] = mock_spidev
mock_pyaudio = MagicMock()
mock_pyaudio.paInt16 = 8
mock_pyaudio.paContinue = 0
sys.modules['pyaudio'] = mock_pyaudio
mock_alsaaudio = MagicMock()
sys.modules['alsaaudio'] = mock_alsaaudio
mock_cv2 = MagicMock()
mock_cv2.VideoCapture.return_value.isOpened.return_value = False
sys.modules['cv2'] = mock_cv2

import importlib
import main
importlib.reload(main)


class TestMainIntegration(unittest.TestCase):
    """Tests verifying main.py wires all components correctly."""

    def test_app_exists(self):
        """Flask app is created."""
        from main import app
        assert app is not None

    def test_socketio_exists(self):
        """SocketIO instance is created."""
        from main import socketio
        assert socketio is not None

    def test_socketio_async_mode_is_threading(self):
        """SocketIO uses threading async mode."""
        from main import socketio
        assert socketio.async_mode == 'threading'

    def test_rover_controller_initialized(self):
        """RoverController is initialized."""
        from main import rover_controller
        assert rover_controller is not None

    def test_video_stream_initialized(self):
        """VideoStream is initialized."""
        from main import video_stream
        assert video_stream is not None

    def test_audio_capture_initialized(self):
        """AudioCapture is initialized."""
        from main import audio_capture
        assert audio_capture is not None

    def test_audio_playback_initialized(self):
        """AudioPlayback is initialized."""
        from main import audio_playback
        assert audio_playback is not None

    def test_video_feed_route_exists(self):
        """The /video_feed route is registered."""
        from main import app
        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert '/video_feed' in rules

    def test_video_feed_returns_503_when_inactive(self):
        """The /video_feed endpoint returns 503 when video is not active."""
        from main import app
        with app.test_client() as client:
            response = client.get('/video_feed')
            assert response.status_code == 503
            data = response.get_json()
            assert data['error'] == 'Video device unavailable'

    def test_404_error_handler(self):
        """Unknown routes return JSON 404 error."""
        from main import app
        with app.test_client() as client:
            response = client.get('/nonexistent')
            assert response.status_code == 404
            data = response.get_json()
            assert data['error'] == 'Not found'

    def test_control_namespace_registered(self):
        """The /control namespace is registered."""
        from main import socketio
        assert '/control' in socketio.server.namespace_handlers

    def test_audio_out_namespace_registered(self):
        """The /audio_out namespace is registered."""
        from main import socketio
        assert '/audio_out' in socketio.server.namespace_handlers

    def test_audio_in_namespace_registered(self):
        """The /audio_in namespace is registered."""
        from main import socketio
        assert '/audio_in' in socketio.server.namespace_handlers


if __name__ == '__main__':
    unittest.main()

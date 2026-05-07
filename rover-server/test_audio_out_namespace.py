"""Unit tests for audio_out_namespace.py — /audio_out WebSocket namespace."""

import sys
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# Mock modules that require hardware
mock_spidev = MagicMock()
sys.modules['spidev'] = mock_spidev
mock_pyaudio = MagicMock()
mock_pyaudio.paInt16 = 8
mock_pyaudio.paContinue = 0
sys.modules['pyaudio'] = mock_pyaudio
mock_alsaaudio = MagicMock()
sys.modules['alsaaudio'] = mock_alsaaudio

from flask import Flask
from flask_socketio import SocketIO

from audio_out_namespace import AudioOutNamespace
from audio_capture import AudioCapture


class TestAudioOutNamespace(unittest.TestCase):
    """Tests for the /audio_out Socket.IO namespace."""

    def setUp(self):
        """Set up Flask test app with SocketIO and a mocked AudioCapture."""
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True

        self.mock_capture = MagicMock(spec=AudioCapture)
        self.mock_capture.is_active = False

        self.socketio = SocketIO(self.app, async_mode='threading')
        self.namespace = AudioOutNamespace('/audio_out', self.mock_capture, self.socketio)
        self.socketio.on_namespace(self.namespace)

        self.client = self.socketio.test_client(
            self.app, namespace='/audio_out'
        )

    def tearDown(self):
        """Disconnect the test client."""
        if self.client.is_connected(namespace='/audio_out'):
            self.client.disconnect(namespace='/audio_out')

    def test_connect(self):
        """Client can connect to /audio_out namespace."""
        assert self.client.is_connected(namespace='/audio_out')

    def test_first_connect_starts_capture(self):
        """First client connection starts audio capture."""
        self.mock_capture.start.assert_called_once()

    def test_first_connect_sets_on_audio_callback(self):
        """First client connection sets the on_audio callback on AudioCapture."""
        # The namespace should have set _on_audio on the capture
        assert self.mock_capture._on_audio is not None

    def test_second_connect_does_not_restart_capture(self):
        """Second client connection does not restart capture when already active."""
        # After first connect, mark as active
        self.mock_capture.is_active = True
        client2 = self.socketio.test_client(self.app, namespace='/audio_out')
        # start should still only have been called once (from first connect)
        self.mock_capture.start.assert_called_once()
        client2.disconnect(namespace='/audio_out')

    def test_disconnect_last_client_stops_capture(self):
        """Disconnecting the last client stops audio capture."""
        self.mock_capture.is_active = True
        self.client.disconnect(namespace='/audio_out')
        self.mock_capture.stop.assert_called_once()

    def test_disconnect_not_last_client_does_not_stop(self):
        """Disconnecting when other clients remain does not stop capture."""
        self.mock_capture.is_active = True
        client2 = self.socketio.test_client(self.app, namespace='/audio_out')
        self.client.disconnect(namespace='/audio_out')
        self.mock_capture.stop.assert_not_called()
        client2.disconnect(namespace='/audio_out')


if __name__ == '__main__':
    unittest.main()

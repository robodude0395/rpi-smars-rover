"""Unit tests for audio_in_namespace.py — /audio_in WebSocket namespace."""

import sys
import unittest
from unittest.mock import MagicMock, patch

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

from audio_in_namespace import AudioInNamespace
from audio_playback import AudioPlayback


class TestAudioInNamespace(unittest.TestCase):
    """Tests for the /audio_in Socket.IO namespace."""

    def setUp(self):
        """Set up Flask test app with SocketIO and a mocked AudioPlayback."""
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True

        self.mock_playback = MagicMock(spec=AudioPlayback)

        self.socketio = SocketIO(self.app, async_mode='threading')
        self.namespace = AudioInNamespace('/audio_in', self.mock_playback)
        self.socketio.on_namespace(self.namespace)

        self.client = self.socketio.test_client(
            self.app, namespace='/audio_in'
        )

    def tearDown(self):
        """Disconnect the test client."""
        if self.client.is_connected(namespace='/audio_in'):
            self.client.disconnect(namespace='/audio_in')

    def test_connect(self):
        """Client can connect to /audio_in namespace."""
        assert self.client.is_connected(namespace='/audio_in')

    def test_first_connect_starts_playback(self):
        """First client connection starts audio playback."""
        # setUp already connected one client
        self.mock_playback.start.assert_called_once()

    def test_second_connect_does_not_restart_playback(self):
        """Second client connection does not restart playback."""
        client2 = self.socketio.test_client(self.app, namespace='/audio_in')
        # start should still only have been called once (from first connect)
        self.mock_playback.start.assert_called_once()
        client2.disconnect(namespace='/audio_in')

    def test_disconnect_last_client_stops_playback(self):
        """Disconnecting the last client stops audio playback."""
        self.client.disconnect(namespace='/audio_in')
        self.mock_playback.stop.assert_called_once()

    def test_disconnect_not_last_client_does_not_stop(self):
        """Disconnecting when other clients remain does not stop playback."""
        client2 = self.socketio.test_client(self.app, namespace='/audio_in')
        self.client.disconnect(namespace='/audio_in')
        self.mock_playback.stop.assert_not_called()
        client2.disconnect(namespace='/audio_in')

    def test_audio_data_writes_to_playback(self):
        """Receiving audio_data event writes data to AudioPlayback."""
        test_data = b'\x00\x01' * 256  # 512 bytes
        self.client.emit('audio_data', test_data, namespace='/audio_in')
        self.mock_playback.write.assert_called_once_with(test_data)

    def test_non_bytes_audio_data_ignored(self):
        """Non-bytes audio data is not written to playback."""
        self.client.emit('audio_data', 'not bytes', namespace='/audio_in')
        self.mock_playback.write.assert_not_called()


if __name__ == '__main__':
    unittest.main()

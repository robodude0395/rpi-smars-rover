"""Socket.IO /audio_in namespace handler for client-to-rover audio.

Receives binary PCM audio frames from the desktop client and writes them
to the AudioPlayback module for speaker output on the rover.
"""

import logging

from flask_socketio import Namespace

logger = logging.getLogger(__name__)


class AudioInNamespace(Namespace):
    """Socket.IO namespace for audio input (client mic → rover speaker) at /audio_in.

    Manages AudioPlayback lifecycle based on client connections:
    - Starts playback when the first client connects
    - Stops playback when the last client disconnects
    - Writes received binary PCM data to the AudioPlayback buffer
    """

    def __init__(self, namespace, audio_playback):
        """Initialize the audio in namespace.

        Args:
            namespace: The Socket.IO namespace path (e.g., '/audio_in').
            audio_playback: An AudioPlayback instance for speaker output.
        """
        super().__init__(namespace)
        self.audio_playback = audio_playback
        self._connected_clients = 0

    def on_connect(self):
        """Handle client connection to /audio_in namespace.

        Starts audio playback when the first client connects.
        """
        self._connected_clients += 1
        logger.info("Client connected to /audio_in (total: %d)", self._connected_clients)

        if self._connected_clients == 1:
            self.audio_playback.start()

    def on_disconnect(self):
        """Handle client disconnect from /audio_in namespace.

        Stops audio playback when the last client disconnects.
        """
        self._connected_clients = max(0, self._connected_clients - 1)
        logger.info("Client disconnected from /audio_in (total: %d)", self._connected_clients)

        if self._connected_clients == 0:
            self.audio_playback.stop()

    def on_audio_data(self, data):
        """Handle incoming binary audio data from the client.

        Writes the received PCM data to the AudioPlayback circular buffer.

        Args:
            data: Raw PCM audio bytes (16-bit signed LE, mono, 16kHz).
        """
        if isinstance(data, (bytes, bytearray)):
            self.audio_playback.write(data)

    def on_set_volume(self, data):
        """Handle volume change from the client.

        Args:
            data: Dict with 'level' key (0-100).
        """
        if isinstance(data, dict) and 'level' in data:
            level = int(data['level'])
            self.audio_playback.set_volume(level)

"""Socket.IO /audio_out namespace handler for rover microphone streaming.

Streams captured audio from the rover's microphone to connected clients
as binary PCM frames (16kHz, mono, 16-bit signed LE). Chunks are batched
to reduce per-packet overhead over high-latency links (e.g. Tailscale).
"""

import logging

from flask_socketio import Namespace

logger = logging.getLogger(__name__)

# Number of capture chunks to batch before emitting.
# At 512 samples/chunk (32ms each), 4 chunks = ~128ms of audio per packet.
# This dramatically reduces Socket.IO framing overhead on WAN links.
BATCH_CHUNKS = 4


class AudioOutNamespace(Namespace):
    """Socket.IO namespace for audio output (rover mic → client) at /audio_out.

    Manages AudioCapture lifecycle based on client connections:
    - Starts capture when the first client connects
    - Stops capture when the last client disconnects
    - Batches PCM chunks and emits to all connected clients
    """

    def __init__(self, namespace, audio_capture, socketio):
        """Initialize the audio out namespace.

        Args:
            namespace: The Socket.IO namespace path (e.g., '/audio_out').
            audio_capture: An AudioCapture instance for microphone capture.
            socketio: The SocketIO app instance (used for emitting to namespace).
        """
        super().__init__(namespace)
        self.audio_capture = audio_capture
        self._socketio = socketio
        self._connected_clients = 0
        self._batch_buffer = bytearray()
        self._batch_target = BATCH_CHUNKS

    def _on_audio_data(self, data):
        """Callback invoked by AudioCapture with PCM audio chunks.

        Accumulates chunks and emits a batched packet once the target count
        is reached. This reduces the number of Socket.IO messages sent over
        the network while keeping latency bounded.

        Args:
            data: Raw PCM audio bytes (512 bytes per chunk from AudioCapture).
        """
        if self._connected_clients <= 0:
            return

        self._batch_buffer.extend(data)

        if len(self._batch_buffer) >= len(data) * self._batch_target:
            try:
                self._socketio.emit('audio_data', bytes(self._batch_buffer),
                                    namespace=self.namespace)
            except Exception as e:
                logger.warning("Failed to emit audio data: %s", e)
            self._batch_buffer.clear()

    def on_connect(self):
        """Handle client connection to /audio_out namespace.

        Starts audio capture when the first client connects.
        """
        self._connected_clients += 1
        logger.info("Client connected to /audio_out (total: %d)", self._connected_clients)

        if self._connected_clients == 1 and not self.audio_capture.is_active:
            self.audio_capture._on_audio = self._on_audio_data
            try:
                self.audio_capture.start()
            except Exception as e:
                logger.error("Failed to start audio capture: %s", e)

    def on_disconnect(self):
        """Handle client disconnect from /audio_out namespace.

        Stops audio capture when the last client disconnects.
        """
        self._connected_clients = max(0, self._connected_clients - 1)
        logger.info("Client disconnected from /audio_out (total: %d)", self._connected_clients)

        if self._connected_clients == 0:
            try:
                if self.audio_capture.is_active:
                    self.audio_capture.stop()
            except Exception as e:
                logger.error("Failed to stop audio capture: %s", e)

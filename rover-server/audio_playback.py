"""Audio playback module for the SMARS Telepresence Rover.

Receives PCM audio data from the client via WebSocket and plays it through
the rover's speaker using ALSA (pyalsaaudio). Uses a circular buffer to
manage latency and prevent buildup.

Audio format: 16kHz, mono, 16-bit signed little-endian (S16_LE).
Buffer capacity: 2 periods (256 samples = 512 bytes).
"""

import logging
import threading
import time
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from gevent import sleep as gevent_sleep
except ImportError:
    gevent_sleep = time.sleep

try:
    import alsaaudio
    _ALSA_AVAILABLE = True
except ImportError:
    _ALSA_AVAILABLE = False
    logger.warning("pyalsaaudio not available — audio playback disabled")


class AudioPlayback:
    """Plays PCM audio through ALSA with a circular buffer.

    Audio is received via the write() method (called from a WebSocket handler
    thread) and played back by a dedicated player thread that reads from a
    circular buffer.

    The circular buffer holds at most 2 periods of audio data. On overflow,
    the oldest data is discarded to retain only the most recent 2 periods.
    """

    SAMPLE_WIDTH = 2  # 16-bit = 2 bytes per sample
    CHANNELS = 1

    def __init__(self, device: str = 'default', sample_rate: int = 16000,
                 period_size: int = 512, max_periods: int = 8):
        """Initialize ALSA playback with circular buffer.

        Args:
            device: ALSA device name (default 'default').
            sample_rate: Sample rate in Hz (default 16000).
            period_size: ALSA period size in samples (default 512).
            max_periods: Maximum number of periods in buffer (default 8).
        """
        self._device = device
        self._sample_rate = sample_rate
        self._period_size = period_size
        self._max_periods = max_periods
        self._max_buffer_bytes = max_periods * period_size * self.SAMPLE_WIDTH
        self._period_bytes = period_size * self.SAMPLE_WIDTH

        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._running = False
        self._player_thread: Optional[threading.Thread] = None
        self._pcm = None
        self._enabled = _ALSA_AVAILABLE

    def start(self):
        """Start the playback thread.

        Opens the ALSA PCM device and starts a background thread that
        reads from the circular buffer and writes to ALSA.
        """
        if not self._enabled:
            logger.warning("Audio playback disabled — pyalsaaudio not available")
            return

        if self._running:
            return

        try:
            self._pcm = alsaaudio.PCM(
                type=alsaaudio.PCM_PLAYBACK,
                mode=alsaaudio.PCM_NORMAL,
                device=self._device
            )
            self._pcm.setchannels(self.CHANNELS)
            self._pcm.setrate(self._sample_rate)
            self._pcm.setformat(alsaaudio.PCM_FORMAT_S16_LE)
            self._pcm.setperiodsize(self._period_size)

            self._running = True
            self._player_thread = threading.Thread(
                target=self._player_loop,
                name="AudioPlaybackThread",
                daemon=True
            )
            self._player_thread.start()
            logger.info("Audio playback started (device=%s, rate=%d, period=%d)",
                        self._device, self._sample_rate, self._period_size)

        except Exception as e:
            logger.error("Failed to open ALSA playback device: %s", e)
            self._cleanup_pcm()

    def stop(self):
        """Stop playback and release resources."""
        if not self._running:
            return

        self._running = False

        if self._player_thread is not None:
            self._player_thread.join(timeout=2.0)
            self._player_thread = None

        self._cleanup_pcm()

        with self._lock:
            self._buffer.clear()

        logger.info("Audio playback stopped")

    def write(self, data: bytes):
        """Write PCM data to circular buffer. Discards oldest on overflow.

        Called from the WebSocket receiver thread. If adding the data would
        exceed the buffer capacity (2 periods), the oldest data is discarded
        to make room, retaining only the most recent 2 periods worth of data.

        Args:
            data: Raw PCM audio bytes (16-bit signed LE, mono, 16kHz).
        """
        if not self._running:
            return

        with self._lock:
            self._buffer.extend(data)

            # If buffer exceeds max capacity, discard oldest data
            if len(self._buffer) > self._max_buffer_bytes:
                overflow = len(self._buffer) - self._max_buffer_bytes
                del self._buffer[:overflow]

    @property
    def buffer_level(self) -> int:
        """Current bytes in buffer."""
        with self._lock:
            return len(self._buffer)

    def _player_loop(self):
        """Background thread that reads from buffer and writes to ALSA.

        Reads one period at a time from the buffer. When the buffer is
        empty, sleeps briefly to avoid busy-waiting.
        """
        while self._running:
            chunk = self._read_period()

            if chunk is None:
                # Buffer empty — sleep briefly to avoid busy-waiting
                gevent_sleep(0.004)  # ~4ms, half a period at 16kHz/512
                continue

            try:
                self._pcm.write(chunk)
            except Exception as e:
                logger.warning("Audio playback error: %s", e)
                # Continue receiving — don't crash on playback errors

    def _read_period(self) -> Optional[bytes]:
        """Read one period of audio from the buffer.

        Returns:
            Bytes of one period, or None if buffer has less than one period.
        """
        with self._lock:
            if len(self._buffer) < self._period_bytes:
                return None

            chunk = bytes(self._buffer[:self._period_bytes])
            del self._buffer[:self._period_bytes]
            return chunk

    def _cleanup_pcm(self):
        """Release ALSA PCM device."""
        if self._pcm is not None:
            try:
                self._pcm.close()
            except Exception as e:
                logger.warning("Error closing ALSA device: %s", e)
            self._pcm = None

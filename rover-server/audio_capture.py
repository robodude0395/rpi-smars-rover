"""Audio capture module for the SMARS Telepresence Rover.

Captures audio from the rover's microphone using PyAudio in callback mode
and delivers 512-byte PCM chunks (256 samples at 16kHz, mono, 16-bit signed)
via a callback function.
"""

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    import pyaudio
    _PYAUDIO_AVAILABLE = True
except ImportError:
    _PYAUDIO_AVAILABLE = False
    logger.warning("PyAudio not available — audio capture disabled")


class AudioCapture:
    """Captures audio from a microphone using PyAudio in callback mode.

    Audio is captured at 16kHz, mono, 16-bit signed format. Captured data
    is delivered as 512-byte chunks (256 samples = 16ms of audio) via the
    on_audio callback.
    """

    FORMAT = pyaudio.paInt16 if _PYAUDIO_AVAILABLE else 8  # paInt16 = 8
    CHANNELS = 1
    SAMPLE_WIDTH = 2  # 16-bit = 2 bytes per sample

    def __init__(self, device_index: Optional[int] = None, sample_rate: int = 16000,
                 chunk_size: int = 256, on_audio: Optional[Callable[[bytes], None]] = None):
        """Initialize audio capture.

        Args:
            device_index: PyAudio device index, or None for system default.
            sample_rate: Sample rate in Hz (default 16000).
            chunk_size: Number of samples per chunk (default 256 = 512 bytes).
            on_audio: Callback invoked with 512-byte PCM chunks.
        """
        self._device_index = device_index
        self._sample_rate = sample_rate
        self._chunk_size = chunk_size
        self._on_audio = on_audio
        self._stream = None
        self._pa = None
        self._active = False
        self._enabled = _PYAUDIO_AVAILABLE

    def start(self):
        """Start capturing audio.

        Opens a PyAudio stream in callback mode. If PyAudio is unavailable
        or the audio device cannot be opened, logs a warning and returns
        without starting capture.
        """
        if not self._enabled:
            logger.warning("Audio capture disabled — PyAudio not available")
            return

        if self._active:
            return

        try:
            self._pa = pyaudio.PyAudio()

            stream_kwargs = {
                'format': self.FORMAT,
                'channels': self.CHANNELS,
                'rate': self._sample_rate,
                'input': True,
                'frames_per_buffer': self._chunk_size,
                'stream_callback': self._audio_callback,
            }

            if self._device_index is not None:
                stream_kwargs['input_device_index'] = self._device_index

            self._stream = self._pa.open(**stream_kwargs)
            self._active = True
            logger.info("Audio capture started (rate=%d, chunk=%d samples)",
                        self._sample_rate, self._chunk_size)

        except Exception as e:
            logger.warning("Failed to open audio device: %s", e)
            self._cleanup()

    def stop(self):
        """Stop capturing audio and release resources."""
        if not self._active:
            return

        self._active = False
        self._cleanup()
        logger.info("Audio capture stopped")

    def _cleanup(self):
        """Release PyAudio stream and instance."""
        if self._stream is not None:
            try:
                if self._stream.is_active():
                    self._stream.stop_stream()
                self._stream.close()
            except Exception as e:
                logger.warning("Error closing audio stream: %s", e)
            self._stream = None

        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception as e:
                logger.warning("Error terminating PyAudio: %s", e)
            self._pa = None

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback invoked when audio data is available.

        Delivers the captured chunk to the on_audio callback.
        """
        if self._on_audio is not None and in_data is not None:
            self._on_audio(in_data)

        if _PYAUDIO_AVAILABLE:
            return (None, pyaudio.paContinue)
        return (None, 0)  # paContinue = 0

    @property
    def is_active(self) -> bool:
        """Whether capture is currently running."""
        return self._active

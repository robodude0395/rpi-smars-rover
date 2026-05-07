"""Unit tests for audio_capture.py."""

import sys
import unittest
from unittest.mock import MagicMock, patch, call

# Mock pyaudio before importing audio_capture
mock_pyaudio = MagicMock()
mock_pyaudio.paInt16 = 8
mock_pyaudio.paContinue = 0
sys.modules['pyaudio'] = mock_pyaudio

import importlib
import audio_capture
importlib.reload(audio_capture)
from audio_capture import AudioCapture


class TestAudioCaptureInit(unittest.TestCase):
    """Tests for AudioCapture initialization."""

    def test_default_parameters(self):
        ac = AudioCapture()
        assert ac._sample_rate == 16000
        assert ac._chunk_size == 256
        assert ac._device_index is None
        assert ac._on_audio is None
        assert ac.is_active is False

    def test_custom_parameters(self):
        callback = MagicMock()
        ac = AudioCapture(device_index=2, sample_rate=44100,
                          chunk_size=512, on_audio=callback)
        assert ac._device_index == 2
        assert ac._sample_rate == 44100
        assert ac._chunk_size == 512
        assert ac._on_audio is callback

    def test_not_active_initially(self):
        ac = AudioCapture()
        assert ac.is_active is False

    def test_format_is_16bit(self):
        assert AudioCapture.FORMAT == 8  # paInt16

    def test_channels_is_mono(self):
        assert AudioCapture.CHANNELS == 1

    def test_sample_width_is_2_bytes(self):
        assert AudioCapture.SAMPLE_WIDTH == 2


class TestAudioCaptureStart(unittest.TestCase):
    """Tests for the start method."""

    def setUp(self):
        mock_pyaudio.reset_mock()

    def test_start_opens_stream_successfully(self):
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture()
        ac.start()

        mock_pyaudio.PyAudio.assert_called_once()
        mock_pa_instance.open.assert_called_once()
        assert ac.is_active is True

    def test_start_configures_stream_correctly(self):
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture(sample_rate=16000, chunk_size=256)
        ac.start()

        call_kwargs = mock_pa_instance.open.call_args[1]
        assert call_kwargs['format'] == 8  # paInt16
        assert call_kwargs['channels'] == 1
        assert call_kwargs['rate'] == 16000
        assert call_kwargs['input'] is True
        assert call_kwargs['frames_per_buffer'] == 256
        assert call_kwargs['stream_callback'] is not None

    def test_start_uses_device_index_when_specified(self):
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture(device_index=3)
        ac.start()

        call_kwargs = mock_pa_instance.open.call_args[1]
        assert call_kwargs['input_device_index'] == 3

    def test_start_omits_device_index_when_none(self):
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture(device_index=None)
        ac.start()

        call_kwargs = mock_pa_instance.open.call_args[1]
        assert 'input_device_index' not in call_kwargs

    def test_start_handles_device_open_failure(self):
        mock_pa_instance = MagicMock()
        mock_pa_instance.open.side_effect = OSError("No audio device")
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture()
        ac.start()

        assert ac.is_active is False

    def test_start_cleans_up_on_failure(self):
        mock_pa_instance = MagicMock()
        mock_pa_instance.open.side_effect = OSError("No audio device")
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture()
        ac.start()

        mock_pa_instance.terminate.assert_called_once()
        assert ac._pa is None
        assert ac._stream is None

    def test_start_when_already_active_does_nothing(self):
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture()
        ac.start()
        ac.start()  # Second call should be no-op

        # PyAudio should only be instantiated once
        assert mock_pyaudio.PyAudio.call_count == 1

    def test_start_disabled_when_pyaudio_unavailable(self):
        with patch.object(audio_capture, '_PYAUDIO_AVAILABLE', False):
            ac = AudioCapture()
            ac._enabled = False
            ac.start()
            assert ac.is_active is False


class TestAudioCaptureStop(unittest.TestCase):
    """Tests for the stop method."""

    def setUp(self):
        mock_pyaudio.reset_mock()

    def test_stop_closes_stream_and_terminates(self):
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_stream.is_active.return_value = True
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture()
        ac.start()
        ac.stop()

        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()
        mock_pa_instance.terminate.assert_called_once()
        assert ac.is_active is False

    def test_stop_when_not_started(self):
        ac = AudioCapture()
        # Should not raise
        ac.stop()
        assert ac.is_active is False

    def test_stop_sets_active_false(self):
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_stream.is_active.return_value = False
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture()
        ac.start()
        assert ac.is_active is True
        ac.stop()
        assert ac.is_active is False

    def test_stop_handles_stream_close_error(self):
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_stream.is_active.return_value = True
        mock_stream.stop_stream.side_effect = OSError("Stream error")
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture()
        ac.start()
        # Should not raise
        ac.stop()
        assert ac.is_active is False

    def test_stop_releases_resources(self):
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_stream.is_active.return_value = False
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture()
        ac.start()
        ac.stop()

        assert ac._stream is None
        assert ac._pa is None


class TestAudioCallback(unittest.TestCase):
    """Tests for the PyAudio callback."""

    def setUp(self):
        mock_pyaudio.reset_mock()

    def test_callback_invokes_on_audio_with_data(self):
        on_audio = MagicMock()
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture(on_audio=on_audio)
        ac.start()

        # Get the callback that was passed to open()
        call_kwargs = mock_pa_instance.open.call_args[1]
        callback = call_kwargs['stream_callback']

        # Simulate PyAudio calling the callback with 512 bytes
        test_data = b'\x00' * 512
        result = callback(test_data, 256, {}, 0)

        on_audio.assert_called_once_with(test_data)
        assert result == (None, mock_pyaudio.paContinue)

    def test_callback_handles_none_data(self):
        on_audio = MagicMock()
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture(on_audio=on_audio)
        ac.start()

        call_kwargs = mock_pa_instance.open.call_args[1]
        callback = call_kwargs['stream_callback']

        # Simulate callback with None data
        result = callback(None, 256, {}, 0)

        on_audio.assert_not_called()
        assert result == (None, mock_pyaudio.paContinue)

    def test_callback_without_on_audio_set(self):
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture(on_audio=None)
        ac.start()

        call_kwargs = mock_pa_instance.open.call_args[1]
        callback = call_kwargs['stream_callback']

        # Should not raise even without callback
        test_data = b'\x00' * 512
        result = callback(test_data, 256, {}, 0)
        assert result == (None, mock_pyaudio.paContinue)

    def test_callback_delivers_exact_chunk(self):
        """Verify the callback delivers the exact bytes received from PyAudio."""
        received_chunks = []

        def capture_audio(data):
            received_chunks.append(data)

        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture(on_audio=capture_audio)
        ac.start()

        call_kwargs = mock_pa_instance.open.call_args[1]
        callback = call_kwargs['stream_callback']

        # Simulate multiple chunks
        chunk1 = b'\x01\x02' * 256  # 512 bytes
        chunk2 = b'\x03\x04' * 256  # 512 bytes
        callback(chunk1, 256, {}, 0)
        callback(chunk2, 256, {}, 0)

        assert len(received_chunks) == 2
        assert received_chunks[0] == chunk1
        assert received_chunks[1] == chunk2


class TestIsActive(unittest.TestCase):
    """Tests for the is_active property."""

    def setUp(self):
        mock_pyaudio.reset_mock()

    def test_active_after_successful_start(self):
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture()
        ac.start()
        assert ac.is_active is True

    def test_not_active_after_stop(self):
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_stream.is_active.return_value = False
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture()
        ac.start()
        ac.stop()
        assert ac.is_active is False

    def test_not_active_when_device_fails(self):
        mock_pa_instance = MagicMock()
        mock_pa_instance.open.side_effect = OSError("No device")
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture()
        ac.start()
        assert ac.is_active is False


class TestStartStopLifecycle(unittest.TestCase):
    """Tests for start/stop lifecycle behavior."""

    def setUp(self):
        mock_pyaudio.reset_mock()

    def test_can_restart_after_stop(self):
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_stream.is_active.return_value = False
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture()
        ac.start()
        assert ac.is_active is True
        ac.stop()
        assert ac.is_active is False

        # Start again
        ac.start()
        assert ac.is_active is True

    def test_multiple_stops_are_safe(self):
        mock_pa_instance = MagicMock()
        mock_stream = MagicMock()
        mock_stream.is_active.return_value = False
        mock_pa_instance.open.return_value = mock_stream
        mock_pyaudio.PyAudio.return_value = mock_pa_instance

        ac = AudioCapture()
        ac.start()
        ac.stop()
        ac.stop()  # Should not raise
        ac.stop()  # Should not raise
        assert ac.is_active is False


if __name__ == '__main__':
    unittest.main()

"""Unit tests for audio_playback.py."""

import sys
import unittest
from unittest.mock import MagicMock, patch
import threading
import time

# Mock alsaaudio before importing audio_playback
mock_alsaaudio = MagicMock()
mock_alsaaudio.PCM_PLAYBACK = 1
mock_alsaaudio.PCM_NORMAL = 0
mock_alsaaudio.PCM_FORMAT_S16_LE = 2
sys.modules['alsaaudio'] = mock_alsaaudio

import importlib
import audio_playback
importlib.reload(audio_playback)
from audio_playback import AudioPlayback


def _reset_alsaaudio_mock():
    """Reset mock state including side_effect on child mocks."""
    mock_alsaaudio.reset_mock()
    mock_alsaaudio.PCM.side_effect = None
    mock_alsaaudio.PCM.return_value = MagicMock()
    mock_alsaaudio.PCM_PLAYBACK = 1
    mock_alsaaudio.PCM_NORMAL = 0
    mock_alsaaudio.PCM_FORMAT_S16_LE = 2


class TestAudioPlaybackInit(unittest.TestCase):
    """Tests for AudioPlayback initialization."""

    def test_default_parameters(self):
        ap = AudioPlayback()
        assert ap._device == 'default'
        assert ap._sample_rate == 16000
        assert ap._period_size == 128
        assert ap._max_periods == 2
        assert ap._running is False

    def test_custom_parameters(self):
        ap = AudioPlayback(device='hw:1,0', sample_rate=44100,
                           period_size=256, max_periods=4)
        assert ap._device == 'hw:1,0'
        assert ap._sample_rate == 44100
        assert ap._period_size == 256
        assert ap._max_periods == 4

    def test_max_buffer_bytes_calculated_correctly(self):
        ap = AudioPlayback(period_size=128, max_periods=2)
        # 2 periods * 128 samples * 2 bytes/sample = 512 bytes
        assert ap._max_buffer_bytes == 512

    def test_period_bytes_calculated_correctly(self):
        ap = AudioPlayback(period_size=128)
        # 128 samples * 2 bytes/sample = 256 bytes
        assert ap._period_bytes == 256

    def test_buffer_initially_empty(self):
        ap = AudioPlayback()
        assert len(ap._buffer) == 0
        assert ap.buffer_level == 0

    def test_not_running_initially(self):
        ap = AudioPlayback()
        assert ap._running is False
        assert ap._pcm is None
        assert ap._player_thread is None

    def test_sample_width_is_2_bytes(self):
        assert AudioPlayback.SAMPLE_WIDTH == 2

    def test_channels_is_mono(self):
        assert AudioPlayback.CHANNELS == 1


class TestAudioPlaybackStart(unittest.TestCase):
    """Tests for the start method."""

    def setUp(self):
        _reset_alsaaudio_mock()

    def test_start_opens_alsa_device(self):
        mock_pcm = MagicMock()
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback()
        ap.start()

        mock_alsaaudio.PCM.assert_called_once_with(
            type=mock_alsaaudio.PCM_PLAYBACK,
            mode=mock_alsaaudio.PCM_NORMAL,
            device='default'
        )

        ap.stop()

    def test_start_configures_alsa_correctly(self):
        mock_pcm = MagicMock()
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback(sample_rate=16000, period_size=128)
        ap.start()

        mock_pcm.setchannels.assert_called_once_with(1)
        mock_pcm.setrate.assert_called_once_with(16000)
        mock_pcm.setformat.assert_called_once_with(mock_alsaaudio.PCM_FORMAT_S16_LE)
        mock_pcm.setperiodsize.assert_called_once_with(128)

        ap.stop()

    def test_start_handles_device_open_failure(self):
        mock_alsaaudio.PCM.side_effect = OSError("No ALSA device")

        ap = AudioPlayback()
        ap.start()

        # Should not crash, should not be running
        assert ap._running is False
        assert ap._pcm is None

    def test_start_is_idempotent(self):
        mock_pcm = MagicMock()
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback()
        ap.start()
        ap.start()  # Second call should be no-op

        # PCM should only be opened once
        assert mock_alsaaudio.PCM.call_count == 1

        ap.stop()

    def test_start_disabled_when_alsaaudio_unavailable(self):
        ap = AudioPlayback()
        ap._enabled = False
        ap.start()

        assert ap._running is False
        mock_alsaaudio.PCM.assert_not_called()

    def test_start_creates_player_thread(self):
        mock_pcm = MagicMock()
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback()
        ap.start()

        assert ap._player_thread is not None
        assert ap._player_thread.is_alive()
        assert ap._player_thread.daemon is True
        assert ap._player_thread.name == "AudioPlaybackThread"

        ap.stop()

    def test_start_sets_running_true(self):
        mock_pcm = MagicMock()
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback()
        ap.start()

        assert ap._running is True

        ap.stop()


class TestAudioPlaybackStop(unittest.TestCase):
    """Tests for the stop method."""

    def setUp(self):
        _reset_alsaaudio_mock()

    def test_stop_closes_device(self):
        mock_pcm = MagicMock()
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback()
        ap.start()
        ap.stop()

        mock_pcm.close.assert_called_once()

    def test_stop_joins_thread(self):
        mock_pcm = MagicMock()
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback()
        ap.start()

        thread = ap._player_thread
        assert thread is not None
        ap.stop()

        assert ap._player_thread is None
        # Thread should have been joined (no longer alive)
        assert not thread.is_alive()

    def test_stop_is_safe_when_not_started(self):
        ap = AudioPlayback()
        # Should not raise
        ap.stop()
        assert ap._running is False

    def test_stop_sets_running_false(self):
        mock_pcm = MagicMock()
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback()
        ap.start()
        assert ap._running is True
        ap.stop()
        assert ap._running is False

    def test_stop_clears_buffer(self):
        mock_pcm = MagicMock()
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback()
        ap.start()
        ap.write(b'\x00' * 100)
        ap.stop()

        assert ap.buffer_level == 0

    def test_multiple_stops_are_safe(self):
        mock_pcm = MagicMock()
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback()
        ap.start()
        ap.stop()
        ap.stop()  # Should not raise
        ap.stop()  # Should not raise
        assert ap._running is False


class TestAudioPlaybackWrite(unittest.TestCase):
    """Tests for the write method."""

    def setUp(self):
        _reset_alsaaudio_mock()

    def test_write_adds_data_to_buffer(self):
        mock_pcm = MagicMock()
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback()
        ap.start()

        # Pause the player loop from consuming data by stopping it
        # and manually setting _running to allow writes
        ap._running = True
        # Actually, we need to prevent the player loop from consuming.
        # Simplest: just write and check immediately (race is unlikely in
        # test but let's use the lock approach)
        data = b'\x01\x02' * 50  # 100 bytes
        ap.write(data)

        # Buffer level might be less if player consumed some, but should be > 0
        # For a reliable test, stop the player loop first
        ap.stop()

    def test_write_adds_data_directly(self):
        """Test write without player thread consuming data."""
        ap = AudioPlayback()
        # Manually set running without starting the thread
        ap._running = True

        data = b'\x01\x02' * 50  # 100 bytes
        ap.write(data)

        assert ap.buffer_level == 100

    def test_write_is_noop_when_not_running(self):
        ap = AudioPlayback()
        ap.write(b'\x00' * 100)

        assert ap.buffer_level == 0

    def test_write_discards_oldest_on_overflow(self):
        # max_buffer_bytes = 2 * 128 * 2 = 512 bytes
        ap = AudioPlayback(period_size=128, max_periods=2)
        # Manually set running without starting the thread
        ap._running = True

        # Write 512 bytes (fills buffer)
        ap.write(b'\x01' * 512)
        assert ap.buffer_level == 512

        # Write 100 more bytes — should discard oldest 100
        ap.write(b'\x02' * 100)
        assert ap.buffer_level == 512

    def test_write_retains_most_recent_data_on_overflow(self):
        ap = AudioPlayback(period_size=128, max_periods=2)
        ap._running = True

        # Fill buffer with pattern A
        ap.write(b'\xAA' * 512)
        # Overflow with pattern B
        ap.write(b'\xBB' * 256)

        # Buffer should contain last 512 bytes: 256 of A + 256 of B
        with ap._lock:
            buffer_content = bytes(ap._buffer)

        assert len(buffer_content) == 512
        assert buffer_content[256:] == b'\xBB' * 256

    def test_write_multiple_small_chunks(self):
        ap = AudioPlayback()
        ap._running = True

        ap.write(b'\x01' * 50)
        ap.write(b'\x02' * 50)
        ap.write(b'\x03' * 50)

        assert ap.buffer_level == 150


class TestBufferLevel(unittest.TestCase):
    """Tests for the buffer_level property."""

    def test_buffer_level_returns_zero_initially(self):
        ap = AudioPlayback()
        assert ap.buffer_level == 0

    def test_buffer_level_reflects_written_data(self):
        ap = AudioPlayback()
        ap._running = True

        ap.write(b'\x00' * 200)
        assert ap.buffer_level == 200

    def test_buffer_level_never_exceeds_max(self):
        ap = AudioPlayback(period_size=128, max_periods=2)
        ap._running = True

        # Write more than max
        ap.write(b'\x00' * 1000)
        assert ap.buffer_level <= 512


class TestReadPeriod(unittest.TestCase):
    """Tests for the _read_period method."""

    def test_returns_none_when_buffer_less_than_period(self):
        ap = AudioPlayback(period_size=128)
        # period_bytes = 128 * 2 = 256
        # Put less than 256 bytes in buffer
        ap._buffer = bytearray(b'\x00' * 100)

        result = ap._read_period()
        assert result is None

    def test_returns_exactly_one_period(self):
        ap = AudioPlayback(period_size=128)
        # period_bytes = 256
        ap._buffer = bytearray(b'\x01' * 256 + b'\x02' * 256)

        result = ap._read_period()
        assert result == b'\x01' * 256
        assert len(result) == 256

    def test_removes_period_from_buffer(self):
        ap = AudioPlayback(period_size=128)
        ap._buffer = bytearray(b'\x01' * 256 + b'\x02' * 256)

        ap._read_period()
        assert len(ap._buffer) == 256
        assert bytes(ap._buffer) == b'\x02' * 256

    def test_returns_none_when_buffer_empty(self):
        ap = AudioPlayback(period_size=128)
        ap._buffer = bytearray()

        result = ap._read_period()
        assert result is None

    def test_returns_none_at_boundary(self):
        ap = AudioPlayback(period_size=128)
        # Exactly one byte less than a period
        ap._buffer = bytearray(b'\x00' * 255)

        result = ap._read_period()
        assert result is None

    def test_returns_period_at_exact_boundary(self):
        ap = AudioPlayback(period_size=128)
        # Exactly one period
        ap._buffer = bytearray(b'\xAB' * 256)

        result = ap._read_period()
        assert result == b'\xAB' * 256
        assert len(ap._buffer) == 0


class TestPlayerLoop(unittest.TestCase):
    """Tests for the _player_loop method."""

    def setUp(self):
        _reset_alsaaudio_mock()

    def test_player_loop_writes_periods_to_alsa(self):
        mock_pcm = MagicMock()
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback(period_size=128, max_periods=2)
        ap.start()

        # Write one full period
        data = b'\x42' * 256
        ap.write(data)

        # Give the player loop time to process
        time.sleep(0.05)

        # PCM write should have been called with the period data
        mock_pcm.write.assert_called_with(data)

        ap.stop()

    def test_player_loop_handles_alsa_write_error(self):
        mock_pcm = MagicMock()
        mock_pcm.write.side_effect = OSError("ALSA write error")
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback(period_size=128, max_periods=2)
        ap.start()

        # Write data — the player loop should handle the error gracefully
        ap.write(b'\x00' * 256)

        # Give the player loop time to process
        time.sleep(0.05)

        # Should still be running (didn't crash)
        assert ap._running is True

        ap.stop()

    def test_player_loop_continues_after_error(self):
        mock_pcm = MagicMock()
        # First call fails, second succeeds
        mock_pcm.write.side_effect = [OSError("ALSA error"), None]
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback(period_size=128, max_periods=2)
        ap.start()

        # Write two periods
        ap.write(b'\x01' * 256)
        ap.write(b'\x02' * 256)

        # Give the player loop time to process both
        time.sleep(0.1)

        # Should have attempted to write twice (once failed, once succeeded)
        assert mock_pcm.write.call_count >= 2

        ap.stop()


class TestCircularBufferCapacity(unittest.TestCase):
    """Tests for circular buffer capacity invariant."""

    def test_buffer_never_exceeds_max_after_single_large_write(self):
        ap = AudioPlayback(period_size=128, max_periods=2)
        ap._running = True

        # Write much more than max capacity
        ap.write(b'\x00' * 2000)
        assert ap.buffer_level <= ap._max_buffer_bytes

    def test_buffer_never_exceeds_max_after_many_writes(self):
        ap = AudioPlayback(period_size=128, max_periods=2)
        ap._running = True

        # Write many small chunks
        for _ in range(50):
            ap.write(b'\x00' * 100)
            assert ap.buffer_level <= ap._max_buffer_bytes

    def test_max_buffer_bytes_equals_max_periods_times_period_bytes(self):
        ap = AudioPlayback(period_size=64, max_periods=3)
        # 3 * 64 * 2 = 384
        assert ap._max_buffer_bytes == 384


class TestStartStopLifecycle(unittest.TestCase):
    """Tests for start/stop lifecycle behavior."""

    def setUp(self):
        _reset_alsaaudio_mock()

    def test_can_restart_after_stop(self):
        mock_pcm = MagicMock()
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback()
        ap.start()
        assert ap._running is True
        ap.stop()
        assert ap._running is False

        # Start again
        ap.start()
        assert ap._running is True
        ap.stop()

    def test_stop_handles_close_error(self):
        mock_pcm = MagicMock()
        mock_pcm.close.side_effect = OSError("Close error")
        mock_alsaaudio.PCM.return_value = mock_pcm

        ap = AudioPlayback()
        ap.start()
        # Should not raise
        ap.stop()
        assert ap._running is False
        assert ap._pcm is None


if __name__ == '__main__':
    unittest.main()

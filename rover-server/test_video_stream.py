"""Unit tests for video_stream.py."""

import sys
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
import numpy as np

# Mock cv2 before importing video_stream
mock_cv2 = MagicMock()
mock_cv2.IMWRITE_JPEG_QUALITY = 1
sys.modules['cv2'] = mock_cv2

import importlib
import video_stream
importlib.reload(video_stream)
from video_stream import VideoStream


class TestVideoStreamInit(unittest.TestCase):
    """Tests for VideoStream initialization."""

    def test_default_parameters(self):
        vs = VideoStream()
        assert vs.device == 0
        assert vs.resolution == (320, 240)
        assert vs.fps == 10
        assert vs.jpeg_quality == 60
        assert vs.is_active is False

    def test_custom_parameters(self):
        vs = VideoStream(device=1, resolution=(640, 480), fps=30, jpeg_quality=80)
        assert vs.device == 1
        assert vs.resolution == (640, 480)
        assert vs.fps == 30
        assert vs.jpeg_quality == 80

    def test_not_active_initially(self):
        vs = VideoStream()
        assert vs.is_active is False


class TestVideoStreamStart(unittest.TestCase):
    """Tests for the start method."""

    def setUp(self):
        mock_cv2.reset_mock()

    def test_start_opens_device_successfully(self):
        mock_capture = MagicMock()
        mock_capture.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_capture

        vs = VideoStream(device=0)
        vs.start()

        mock_cv2.VideoCapture.assert_called_with(0)
        assert vs.is_active is True

    def test_start_with_different_device(self):
        mock_capture = MagicMock()
        mock_capture.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_capture

        vs = VideoStream(device=2)
        vs.start()

        mock_cv2.VideoCapture.assert_called_with(2)
        assert vs.is_active is True

    def test_start_fails_when_device_unavailable(self):
        mock_capture = MagicMock()
        mock_capture.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = mock_capture

        vs = VideoStream(device=0)
        vs.start()

        assert vs.is_active is False

    def test_start_fails_when_cv2_unavailable(self):
        with patch.object(video_stream, '_CV2_AVAILABLE', False):
            vs = VideoStream()
            vs.start()
            assert vs.is_active is False


class TestVideoStreamStop(unittest.TestCase):
    """Tests for the stop method."""

    def setUp(self):
        mock_cv2.reset_mock()

    def test_stop_releases_capture(self):
        mock_capture = MagicMock()
        mock_capture.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_capture

        vs = VideoStream()
        vs.start()
        vs.stop()

        mock_capture.release.assert_called_once()
        assert vs.is_active is False

    def test_stop_when_not_started(self):
        vs = VideoStream()
        # Should not raise
        vs.stop()
        assert vs.is_active is False


class TestGenerateFrames(unittest.TestCase):
    """Tests for the generate_frames method."""

    def setUp(self):
        mock_cv2.reset_mock()
        # Clear any side_effects from previous tests
        mock_cv2.imencode.side_effect = None
        mock_cv2.imencode.return_value = None
        mock_cv2.resize.side_effect = None
        mock_cv2.resize.return_value = None

    def _create_active_stream(self):
        """Helper to create a started VideoStream with mocked capture."""
        mock_capture = MagicMock()
        mock_capture.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_capture

        vs = VideoStream(device=0, resolution=(320, 240), fps=10, jpeg_quality=60)
        vs.start()
        return vs, mock_capture

    def test_yields_nothing_when_not_active(self):
        vs = VideoStream()
        frames = list(vs.generate_frames())
        assert frames == []

    @patch('video_stream.time')
    def test_yields_multipart_formatted_frame(self, mock_time):
        mock_time.time.return_value = 0.0

        vs, mock_capture = self._create_active_stream()

        # Simulate one successful frame then stop
        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_capture.read.return_value = (True, fake_frame)

        fake_resized = np.zeros((240, 320, 3), dtype=np.uint8)
        mock_cv2.resize.return_value = fake_resized

        fake_jpeg = MagicMock()
        fake_jpeg.tobytes.return_value = b'\xff\xd8\xff\xe0JFIF_DATA'
        mock_cv2.imencode.return_value = (True, fake_jpeg)

        # Get one frame then stop the stream
        gen = vs.generate_frames()
        frame = next(gen)
        vs.stop()

        # Verify multipart format
        assert frame.startswith(b'--frame\r\nContent-Type: image/jpeg\r\n\r\n')
        assert frame.endswith(b'\r\n')
        assert b'\xff\xd8\xff\xe0JFIF_DATA' in frame

    @patch('video_stream.time')
    def test_frame_is_resized_to_configured_resolution(self, mock_time):
        mock_time.time.return_value = 0.0

        vs, mock_capture = self._create_active_stream()

        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_capture.read.return_value = (True, fake_frame)

        fake_resized = np.zeros((240, 320, 3), dtype=np.uint8)
        mock_cv2.resize.return_value = fake_resized

        fake_jpeg = MagicMock()
        fake_jpeg.tobytes.return_value = b'jpeg_data'
        mock_cv2.imencode.return_value = (True, fake_jpeg)

        gen = vs.generate_frames()
        next(gen)
        vs.stop()

        mock_cv2.resize.assert_called_with(fake_frame, (320, 240))

    @patch('video_stream.time')
    def test_jpeg_encoded_with_configured_quality(self, mock_time):
        mock_time.time.return_value = 0.0

        vs, mock_capture = self._create_active_stream()

        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_capture.read.return_value = (True, fake_frame)

        fake_resized = np.zeros((240, 320, 3), dtype=np.uint8)
        mock_cv2.resize.return_value = fake_resized

        fake_jpeg = MagicMock()
        fake_jpeg.tobytes.return_value = b'jpeg_data'
        mock_cv2.imencode.return_value = (True, fake_jpeg)

        gen = vs.generate_frames()
        next(gen)
        vs.stop()

        mock_cv2.imencode.assert_called_with(
            '.jpg', fake_resized, [mock_cv2.IMWRITE_JPEG_QUALITY, 60]
        )

    @patch('video_stream.time')
    def test_skips_frame_on_capture_failure(self, mock_time):
        mock_time.time.return_value = 0.0

        vs, mock_capture = self._create_active_stream()

        # First read fails, second succeeds, then stop
        fake_frame = np.zeros((240, 320, 3), dtype=np.uint8)
        mock_capture.read.side_effect = [
            (False, None),
            (True, fake_frame),
        ]

        mock_cv2.resize.return_value = fake_frame
        fake_jpeg = MagicMock()
        fake_jpeg.tobytes.return_value = b'jpeg_data'
        mock_cv2.imencode.return_value = (True, fake_jpeg)

        gen = vs.generate_frames()
        frame = next(gen)
        vs.stop()

        # Should have called read twice (first failed, second succeeded)
        assert mock_capture.read.call_count == 2
        assert b'jpeg_data' in frame

    @patch('video_stream.time')
    def test_skips_frame_on_encode_failure(self, mock_time):
        mock_time.time.return_value = 0.0

        vs, mock_capture = self._create_active_stream()

        fake_frame = np.zeros((240, 320, 3), dtype=np.uint8)
        mock_capture.read.return_value = (True, fake_frame)
        mock_cv2.resize.return_value = fake_frame

        fake_jpeg = MagicMock()
        fake_jpeg.tobytes.return_value = b'good_jpeg'

        # First encode fails, second succeeds
        mock_cv2.imencode.side_effect = [
            (False, None),
            (True, fake_jpeg),
        ]

        gen = vs.generate_frames()
        frame = next(gen)
        vs.stop()

        # Should have encoded twice (first failed, second succeeded)
        assert mock_cv2.imencode.call_count == 2
        assert b'good_jpeg' in frame

    @patch('video_stream.time')
    def test_frame_pacing_sleeps_for_remaining_interval(self, mock_time):
        """Verify that frame pacing sleeps to maintain target FPS."""
        # Simulate frame processing taking 0.02s (20ms) at 10fps (100ms interval)
        mock_time.time.side_effect = [0.0, 0.02, 0.1, 0.12]

        vs, mock_capture = self._create_active_stream()

        fake_frame = np.zeros((240, 320, 3), dtype=np.uint8)
        mock_capture.read.return_value = (True, fake_frame)
        mock_cv2.resize.return_value = fake_frame

        fake_jpeg = MagicMock()
        fake_jpeg.tobytes.return_value = b'jpeg_data'
        mock_cv2.imencode.return_value = (True, fake_jpeg)

        gen = vs.generate_frames()
        next(gen)
        vs.stop()

        # Should sleep for frame_interval - elapsed = 0.1 - 0.02 = 0.08
        mock_time.sleep.assert_called_with(0.08)

    @patch('video_stream.time')
    def test_no_sleep_when_processing_exceeds_interval(self, mock_time):
        """Verify no sleep when frame processing takes longer than interval."""
        # Simulate frame processing taking 0.15s at 10fps (100ms interval)
        mock_time.time.side_effect = [0.0, 0.15, 0.2, 0.35]

        vs, mock_capture = self._create_active_stream()

        fake_frame = np.zeros((240, 320, 3), dtype=np.uint8)
        mock_capture.read.return_value = (True, fake_frame)
        mock_cv2.resize.return_value = fake_frame

        fake_jpeg = MagicMock()
        fake_jpeg.tobytes.return_value = b'jpeg_data'
        mock_cv2.imencode.return_value = (True, fake_jpeg)

        gen = vs.generate_frames()
        next(gen)
        vs.stop()

        # Should NOT call sleep since elapsed > frame_interval
        mock_time.sleep.assert_not_called()


class TestIsActive(unittest.TestCase):
    """Tests for the is_active property."""

    def setUp(self):
        mock_cv2.reset_mock()

    def test_active_after_successful_start(self):
        mock_capture = MagicMock()
        mock_capture.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_capture

        vs = VideoStream()
        vs.start()
        assert vs.is_active is True

    def test_not_active_after_stop(self):
        mock_capture = MagicMock()
        mock_capture.isOpened.return_value = True
        mock_cv2.VideoCapture.return_value = mock_capture

        vs = VideoStream()
        vs.start()
        vs.stop()
        assert vs.is_active is False

    def test_not_active_when_device_fails(self):
        mock_capture = MagicMock()
        mock_capture.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = mock_capture

        vs = VideoStream()
        vs.start()
        assert vs.is_active is False


if __name__ == '__main__':
    unittest.main()

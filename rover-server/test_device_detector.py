"""Unit tests for device_detector.py.

All subprocess calls are mocked to test parsing logic without requiring
actual hardware or system utilities.
"""

import subprocess
import unittest
from unittest.mock import patch, MagicMock

from device_detector import DeviceDetector


class TestListVideoDevices(unittest.TestCase):
    """Tests for DeviceDetector.list_video_devices()."""

    @patch('device_detector.subprocess.run')
    def test_returns_empty_list_when_v4l2ctl_not_found(self, mock_run):
        """Requirement 7.3: missing v4l2-ctl returns empty list."""
        mock_run.side_effect = FileNotFoundError("No such file or directory")
        result = DeviceDetector.list_video_devices()
        assert result == []

    @patch('device_detector.subprocess.run')
    def test_logs_error_when_v4l2ctl_not_found(self, mock_run):
        """Requirement 7.3: missing v4l2-ctl logs error."""
        mock_run.side_effect = FileNotFoundError("No such file or directory")
        with self.assertLogs('device_detector', level='ERROR') as cm:
            DeviceDetector.list_video_devices()
        assert any('v4l2-ctl not found' in msg for msg in cm.output)

    @patch('device_detector.subprocess.run')
    def test_returns_empty_list_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='v4l2-ctl', timeout=10)
        result = DeviceDetector.list_video_devices()
        assert result == []

    @patch('device_detector.subprocess.run')
    def test_returns_empty_list_when_no_devices(self, mock_run):
        mock_run.return_value = MagicMock(stdout='', returncode=0)
        result = DeviceDetector.list_video_devices()
        assert result == []

    @patch('device_detector.subprocess.run')
    def test_parses_single_device(self, mock_run):
        """Requirement 7.1: enumerate V4L2 devices with path and name."""
        list_output = (
            "USB Camera (usb-0000:00:14.0-1):\n"
            "\t/dev/video0\n"
            "\t/dev/video1\n"
            "\n"
        )
        formats_output = (
            "ioctl: VIDIOC_ENUM_FMT\n"
            "\tType: Video Capture\n"
            "\n"
            "\t[0]: 'MJPG' (Motion-JPEG, compressed)\n"
            "\t\tSize: Discrete 640x480\n"
            "\t\t\tInterval: Discrete 0.033s (30.000 fps)\n"
            "\t\t\tInterval: Discrete 0.067s (15.000 fps)\n"
            "\t\tSize: Discrete 320x240\n"
            "\t\t\tInterval: Discrete 0.033s (30.000 fps)\n"
            "\t[1]: 'YUYV' (YUYV 4:2:2)\n"
            "\t\tSize: Discrete 640x480\n"
            "\t\t\tInterval: Discrete 0.100s (10.000 fps)\n"
        )

        def side_effect(cmd, **kwargs):
            if '--list-devices' in cmd:
                return MagicMock(stdout=list_output, returncode=0)
            elif '--list-formats-ext' in cmd:
                return MagicMock(stdout=formats_output, returncode=0)
            return MagicMock(stdout='', returncode=0)

        mock_run.side_effect = side_effect
        result = DeviceDetector.list_video_devices()

        # Should find two /dev/video entries
        assert len(result) == 2
        assert result[0]['path'] == '/dev/video0'
        assert result[0]['name'] == 'USB Camera'
        assert 'MJPG' in result[0]['formats']
        assert 'YUYV' in result[0]['formats']
        assert '640x480' in result[0]['resolutions']
        assert '320x240' in result[0]['resolutions']
        assert 30 in result[0]['framerates']
        assert 15 in result[0]['framerates']
        assert 10 in result[0]['framerates']

    @patch('device_detector.subprocess.run')
    def test_parses_multiple_devices(self, mock_run):
        list_output = (
            "USB Camera (usb-0000:00:14.0-1):\n"
            "\t/dev/video0\n"
            "\n"
            "HD Webcam (usb-0000:00:14.0-2):\n"
            "\t/dev/video2\n"
            "\n"
        )
        formats_output = (
            "\t[0]: 'MJPG' (Motion-JPEG)\n"
            "\t\tSize: Discrete 1920x1080\n"
            "\t\t\tInterval: Discrete 0.033s (30.000 fps)\n"
        )

        def side_effect(cmd, **kwargs):
            if '--list-devices' in cmd:
                return MagicMock(stdout=list_output, returncode=0)
            elif '--list-formats-ext' in cmd:
                return MagicMock(stdout=formats_output, returncode=0)
            return MagicMock(stdout='', returncode=0)

        mock_run.side_effect = side_effect
        result = DeviceDetector.list_video_devices()

        assert len(result) == 2
        assert result[0]['path'] == '/dev/video0'
        assert result[0]['name'] == 'USB Camera'
        assert result[1]['path'] == '/dev/video2'
        assert result[1]['name'] == 'HD Webcam'

    @patch('device_detector.subprocess.run')
    def test_handles_format_query_failure(self, mock_run):
        """If format query fails, device still returned with empty capabilities."""
        list_output = "Camera (usb-1):\n\t/dev/video0\n\n"

        call_count = [0]

        def side_effect(cmd, **kwargs):
            call_count[0] += 1
            if '--list-devices' in cmd:
                return MagicMock(stdout=list_output, returncode=0)
            elif '--list-formats-ext' in cmd:
                raise subprocess.TimeoutExpired(cmd='v4l2-ctl', timeout=10)
            return MagicMock(stdout='', returncode=0)

        mock_run.side_effect = side_effect
        result = DeviceDetector.list_video_devices()

        assert len(result) == 1
        assert result[0]['path'] == '/dev/video0'
        assert result[0]['formats'] == []
        assert result[0]['resolutions'] == []
        assert result[0]['framerates'] == []


class TestListAudioDevices(unittest.TestCase):
    """Tests for DeviceDetector.list_audio_devices()."""

    @patch('device_detector.subprocess.run')
    def test_returns_empty_list_when_arecord_not_found(self, mock_run):
        """Requirement 7.4: missing arecord returns empty list."""
        mock_run.side_effect = FileNotFoundError("No such file or directory")
        result = DeviceDetector.list_audio_devices()
        assert result == []

    @patch('device_detector.subprocess.run')
    def test_logs_error_when_arecord_not_found(self, mock_run):
        """Requirement 7.4: missing arecord logs error."""
        mock_run.side_effect = FileNotFoundError("No such file or directory")
        with self.assertLogs('device_detector', level='ERROR') as cm:
            DeviceDetector.list_audio_devices()
        assert any('arecord not found' in msg for msg in cm.output)

    @patch('device_detector.subprocess.run')
    def test_returns_empty_list_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='arecord', timeout=10)
        result = DeviceDetector.list_audio_devices()
        assert result == []

    @patch('device_detector.subprocess.run')
    def test_returns_empty_list_when_no_devices(self, mock_run):
        mock_run.return_value = MagicMock(stdout='', returncode=0)
        result = DeviceDetector.list_audio_devices()
        assert result == []

    @patch('device_detector.subprocess.run')
    def test_parses_single_audio_device(self, mock_run):
        """Requirement 7.2: enumerate ALSA audio devices with path and name."""
        list_output = (
            "**** List of CAPTURE Hardware Devices ****\n"
            "card 1: Microphone [USB Microphone], device 0: USB Audio [USB Audio]\n"
            "  Subdevices: 1/1\n"
            "  Subdevice #0: subdevice #0\n"
        )
        hw_params_output = (
            "Recording WAVE '/dev/null' : Signed 16 bit Little Endian, "
            "Rate 16000 Hz, Mono\n"
            "HW Params of device \"hw:1,0\":\n"
            "--------------------\n"
            "ACCESS: MMAP_INTERLEAVED RW_INTERLEAVED\n"
            "FORMAT: S16_LE S32_LE\n"
            "SUBFORMAT: STD\n"
            "SAMPLE_BITS: [16 32]\n"
            "FRAME_BITS: [16 64]\n"
            "CHANNELS: [1 2]\n"
            "RATE: [8000 48000]\n"
            "PERIOD_TIME: [1000 128000000]\n"
            "PERIOD_SIZE: [8 1024000]\n"
            "PERIOD_BYTES: [128 8192000]\n"
            "PERIODS: [2 1024]\n"
            "BUFFER_TIME: [2000 256000000]\n"
            "BUFFER_SIZE: [16 2048000]\n"
            "BUFFER_BYTES: [128 16384000]\n"
            "TICK_TIME: 0\n"
        )

        def side_effect(cmd, **kwargs):
            if cmd[0] == 'arecord' and '-l' in cmd:
                return MagicMock(stdout=list_output, stderr='', returncode=0)
            elif cmd[0] == 'arecord' and '--dump-hw-params' in cmd:
                return MagicMock(stdout='', stderr=hw_params_output, returncode=1)
            return MagicMock(stdout='', stderr='', returncode=0)

        mock_run.side_effect = side_effect
        result = DeviceDetector.list_audio_devices()

        assert len(result) == 1
        assert result[0]['device'] == 'hw:1,0'
        assert result[0]['name'] == 'USB Microphone'
        assert 'S16_LE' in result[0]['formats']
        assert 'S32_LE' in result[0]['formats']
        assert 16000 in result[0]['sample_rates']
        assert 44100 in result[0]['sample_rates']
        assert 48000 in result[0]['sample_rates']
        assert 1 in result[0]['channels']
        assert 2 in result[0]['channels']

    @patch('device_detector.subprocess.run')
    def test_parses_multiple_audio_devices(self, mock_run):
        list_output = (
            "**** List of CAPTURE Hardware Devices ****\n"
            "card 0: PCH [HDA Intel PCH], device 0: ALC892 Analog [ALC892 Analog]\n"
            "  Subdevices: 1/1\n"
            "  Subdevice #0: subdevice #0\n"
            "card 1: Microphone [USB Microphone], device 0: USB Audio [USB Audio]\n"
            "  Subdevices: 1/1\n"
            "  Subdevice #0: subdevice #0\n"
        )

        def side_effect(cmd, **kwargs):
            if cmd[0] == 'arecord' and '-l' in cmd:
                return MagicMock(stdout=list_output, stderr='', returncode=0)
            elif cmd[0] == 'arecord' and '--dump-hw-params' in cmd:
                return MagicMock(stdout='', stderr='', returncode=1)
            return MagicMock(stdout='', stderr='', returncode=0)

        mock_run.side_effect = side_effect
        result = DeviceDetector.list_audio_devices()

        assert len(result) == 2
        assert result[0]['device'] == 'hw:0,0'
        assert result[0]['name'] == 'HDA Intel PCH'
        assert result[1]['device'] == 'hw:1,0'
        assert result[1]['name'] == 'USB Microphone'

    @patch('device_detector.subprocess.run')
    def test_handles_hw_params_query_failure(self, mock_run):
        """If hw params query fails, device still returned with empty capabilities."""
        list_output = (
            "**** List of CAPTURE Hardware Devices ****\n"
            "card 1: Mic [USB Mic], device 0: USB Audio [USB Audio]\n"
            "  Subdevices: 1/1\n"
        )

        def side_effect(cmd, **kwargs):
            if cmd[0] == 'arecord' and '-l' in cmd:
                return MagicMock(stdout=list_output, stderr='', returncode=0)
            elif cmd[0] == 'arecord' and '--dump-hw-params' in cmd:
                raise subprocess.TimeoutExpired(cmd='arecord', timeout=5)
            return MagicMock(stdout='', stderr='', returncode=0)

        mock_run.side_effect = side_effect
        result = DeviceDetector.list_audio_devices()

        assert len(result) == 1
        assert result[0]['device'] == 'hw:1,0'
        assert result[0]['name'] == 'USB Mic'
        assert result[0]['formats'] == []
        assert result[0]['sample_rates'] == []
        assert result[0]['channels'] == []


class TestParseV4l2DeviceList(unittest.TestCase):
    """Tests for the V4L2 device list parser."""

    def test_empty_output(self):
        result = DeviceDetector._parse_v4l2_device_list('')
        assert result == []

    def test_none_like_output(self):
        result = DeviceDetector._parse_v4l2_device_list('   \n  \n')
        assert result == []

    def test_standard_format(self):
        output = (
            "USB Camera (usb-0000:00:14.0-1):\n"
            "\t/dev/video0\n"
            "\t/dev/video1\n"
            "\n"
        )
        result = DeviceDetector._parse_v4l2_device_list(output)
        assert len(result) == 2
        assert result[0]['path'] == '/dev/video0'
        assert result[0]['name'] == 'USB Camera'
        assert result[1]['path'] == '/dev/video1'
        assert result[1]['name'] == 'USB Camera'

    def test_multiple_device_groups(self):
        output = (
            "Camera A (usb-1):\n"
            "\t/dev/video0\n"
            "\n"
            "Camera B (usb-2):\n"
            "\t/dev/video2\n"
            "\t/dev/video3\n"
            "\n"
        )
        result = DeviceDetector._parse_v4l2_device_list(output)
        assert len(result) == 3
        assert result[0]['name'] == 'Camera A'
        assert result[1]['name'] == 'Camera B'
        assert result[2]['name'] == 'Camera B'


class TestQueryV4l2Formats(unittest.TestCase):
    """Tests for the V4L2 format query parser."""

    @patch('device_detector.subprocess.run')
    def test_parses_formats_resolutions_framerates(self, mock_run):
        output = (
            "ioctl: VIDIOC_ENUM_FMT\n"
            "\tType: Video Capture\n"
            "\n"
            "\t[0]: 'MJPG' (Motion-JPEG, compressed)\n"
            "\t\tSize: Discrete 1920x1080\n"
            "\t\t\tInterval: Discrete 0.033s (30.000 fps)\n"
            "\t\t\tInterval: Discrete 0.067s (15.000 fps)\n"
            "\t\tSize: Discrete 1280x720\n"
            "\t\t\tInterval: Discrete 0.033s (30.000 fps)\n"
            "\t[1]: 'YUYV' (YUYV 4:2:2)\n"
            "\t\tSize: Discrete 640x480\n"
            "\t\t\tInterval: Discrete 0.100s (10.000 fps)\n"
        )
        mock_run.return_value = MagicMock(stdout=output, returncode=0)

        formats, resolutions, framerates = DeviceDetector._query_v4l2_formats('/dev/video0')

        assert formats == ['MJPG', 'YUYV']
        assert '1920x1080' in resolutions
        assert '1280x720' in resolutions
        assert '640x480' in resolutions
        assert framerates == [10, 15, 30]

    @patch('device_detector.subprocess.run')
    def test_no_duplicate_formats(self, mock_run):
        output = (
            "\t[0]: 'MJPG' (Motion-JPEG)\n"
            "\t\tSize: Discrete 640x480\n"
            "\t\t\tInterval: Discrete 0.033s (30.000 fps)\n"
            "\t\tSize: Discrete 640x480\n"
            "\t\t\tInterval: Discrete 0.033s (30.000 fps)\n"
        )
        mock_run.return_value = MagicMock(stdout=output, returncode=0)

        formats, resolutions, framerates = DeviceDetector._query_v4l2_formats('/dev/video0')

        assert formats == ['MJPG']
        assert resolutions == ['640x480']
        assert framerates == [30]

    @patch('device_detector.subprocess.run')
    def test_empty_output(self, mock_run):
        mock_run.return_value = MagicMock(stdout='', returncode=0)
        formats, resolutions, framerates = DeviceDetector._query_v4l2_formats('/dev/video0')
        assert formats == []
        assert resolutions == []
        assert framerates == []


class TestParseArecordDeviceList(unittest.TestCase):
    """Tests for the arecord device list parser."""

    def test_empty_output(self):
        result = DeviceDetector._parse_arecord_device_list('')
        assert result == []

    def test_standard_format(self):
        output = (
            "**** List of CAPTURE Hardware Devices ****\n"
            "card 1: Microphone [USB Microphone], device 0: USB Audio [USB Audio]\n"
            "  Subdevices: 1/1\n"
            "  Subdevice #0: subdevice #0\n"
        )
        result = DeviceDetector._parse_arecord_device_list(output)
        assert len(result) == 1
        assert result[0]['device'] == 'hw:1,0'
        assert result[0]['name'] == 'USB Microphone'

    def test_multiple_cards(self):
        output = (
            "**** List of CAPTURE Hardware Devices ****\n"
            "card 0: PCH [HDA Intel PCH], device 0: ALC892 [ALC892 Analog]\n"
            "  Subdevices: 1/1\n"
            "card 2: Webcam [HD Webcam], device 0: USB Audio [USB Audio]\n"
            "  Subdevices: 1/1\n"
        )
        result = DeviceDetector._parse_arecord_device_list(output)
        assert len(result) == 2
        assert result[0]['device'] == 'hw:0,0'
        assert result[0]['name'] == 'HDA Intel PCH'
        assert result[1]['device'] == 'hw:2,0'
        assert result[1]['name'] == 'HD Webcam'

    def test_no_capture_devices(self):
        output = "**** List of CAPTURE Hardware Devices ****\n"
        result = DeviceDetector._parse_arecord_device_list(output)
        assert result == []


class TestQueryAudioParams(unittest.TestCase):
    """Tests for the audio hardware params query."""

    @patch('device_detector.subprocess.run')
    def test_parses_range_format(self, mock_run):
        """Parse [min max] range format for rates and channels."""
        hw_output = (
            "FORMAT: S16_LE S32_LE\n"
            "CHANNELS: [1 2]\n"
            "RATE: [8000 48000]\n"
        )
        mock_run.return_value = MagicMock(stdout='', stderr=hw_output, returncode=1)

        formats, sample_rates, channels = DeviceDetector._query_audio_params('hw:1,0')

        assert 'S16_LE' in formats
        assert 'S32_LE' in formats
        assert 1 in channels
        assert 2 in channels
        # Common rates within [8000, 48000]
        assert 8000 in sample_rates
        assert 16000 in sample_rates
        assert 44100 in sample_rates
        assert 48000 in sample_rates
        # 96000 should NOT be included
        assert 96000 not in sample_rates

    @patch('device_detector.subprocess.run')
    def test_parses_individual_values(self, mock_run):
        """Parse space-separated individual values."""
        hw_output = (
            "FORMAT: S16_LE\n"
            "CHANNELS: 1\n"
            "RATE: 16000 44100 48000\n"
        )
        mock_run.return_value = MagicMock(stdout=hw_output, stderr='', returncode=0)

        formats, sample_rates, channels = DeviceDetector._query_audio_params('hw:0,0')

        assert formats == ['S16_LE']
        assert sample_rates == [16000, 44100, 48000]
        assert channels == [1]

    @patch('device_detector.subprocess.run')
    def test_handles_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='arecord', timeout=5)
        formats, sample_rates, channels = DeviceDetector._query_audio_params('hw:1,0')
        assert formats == []
        assert sample_rates == []
        assert channels == []

    @patch('device_detector.subprocess.run')
    def test_handles_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        formats, sample_rates, channels = DeviceDetector._query_audio_params('hw:1,0')
        assert formats == []
        assert sample_rates == []
        assert channels == []

    @patch('device_detector.subprocess.run')
    def test_handles_empty_output(self, mock_run):
        mock_run.return_value = MagicMock(stdout='', stderr='', returncode=1)
        formats, sample_rates, channels = DeviceDetector._query_audio_params('hw:1,0')
        assert formats == []
        assert sample_rates == []
        assert channels == []


class TestReturnFormat(unittest.TestCase):
    """Tests verifying the return format matches the design spec."""

    @patch('device_detector.subprocess.run')
    def test_video_device_return_format(self, mock_run):
        """Verify video device dict has all required keys."""
        list_output = "Camera (usb-1):\n\t/dev/video0\n\n"
        formats_output = (
            "\t[0]: 'MJPG' (Motion-JPEG)\n"
            "\t\tSize: Discrete 320x240\n"
            "\t\t\tInterval: Discrete 0.033s (30.000 fps)\n"
        )

        def side_effect(cmd, **kwargs):
            if '--list-devices' in cmd:
                return MagicMock(stdout=list_output, returncode=0)
            return MagicMock(stdout=formats_output, returncode=0)

        mock_run.side_effect = side_effect
        result = DeviceDetector.list_video_devices()

        assert len(result) == 1
        device = result[0]
        assert 'path' in device
        assert 'name' in device
        assert 'formats' in device
        assert 'resolutions' in device
        assert 'framerates' in device
        assert isinstance(device['formats'], list)
        assert isinstance(device['resolutions'], list)
        assert isinstance(device['framerates'], list)

    @patch('device_detector.subprocess.run')
    def test_audio_device_return_format(self, mock_run):
        """Verify audio device dict has all required keys."""
        list_output = (
            "**** List of CAPTURE Hardware Devices ****\n"
            "card 1: Mic [USB Mic], device 0: Audio [USB Audio]\n"
            "  Subdevices: 1/1\n"
        )
        hw_output = "FORMAT: S16_LE\nCHANNELS: [1 2]\nRATE: [16000 48000]\n"

        def side_effect(cmd, **kwargs):
            if cmd[0] == 'arecord' and '-l' in cmd:
                return MagicMock(stdout=list_output, stderr='', returncode=0)
            elif cmd[0] == 'arecord' and '--dump-hw-params' in cmd:
                return MagicMock(stdout='', stderr=hw_output, returncode=1)
            return MagicMock(stdout='', stderr='', returncode=0)

        mock_run.side_effect = side_effect
        result = DeviceDetector.list_audio_devices()

        assert len(result) == 1
        device = result[0]
        assert 'device' in device
        assert 'name' in device
        assert 'formats' in device
        assert 'sample_rates' in device
        assert 'channels' in device
        assert isinstance(device['formats'], list)
        assert isinstance(device['sample_rates'], list)
        assert isinstance(device['channels'], list)


if __name__ == '__main__':
    unittest.main()

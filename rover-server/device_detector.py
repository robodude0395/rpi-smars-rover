"""Hardware device detection for the SMARS Telepresence Rover.

Enumerates V4L2 video devices and ALSA audio input devices by calling
system utilities (v4l2-ctl, arecord) as subprocesses. Returns structured
device information including capabilities (formats, resolutions, frame rates,
sample rates, channels).

If the required system tools are not installed, returns empty lists and logs
an error indicating the missing dependency.
"""

import logging
import re
import subprocess

logger = logging.getLogger(__name__)


class DeviceDetector:
    """Detects available video and audio hardware on the system."""

    @staticmethod
    def list_video_devices() -> list[dict]:
        """Enumerate V4L2 video devices with capabilities.

        Calls v4l2-ctl --list-devices to find devices, then queries each
        device with v4l2-ctl --list-formats-ext for format details.

        Returns:
            List of dicts with keys: path, name, formats, resolutions, framerates.
            Returns empty list if v4l2-ctl is not installed.
        """
        try:
            result = subprocess.run(
                ['v4l2-ctl', '--list-devices'],
                capture_output=True, text=True, timeout=10
            )
        except FileNotFoundError:
            logger.error(
                "v4l2-ctl not found. Install v4l-utils to enable video device detection."
            )
            return []
        except subprocess.TimeoutExpired:
            logger.error("v4l2-ctl --list-devices timed out.")
            return []

        devices = DeviceDetector._parse_v4l2_device_list(result.stdout)

        # Query each device for format details
        for device in devices:
            formats, resolutions, framerates = DeviceDetector._query_v4l2_formats(
                device['path']
            )
            device['formats'] = formats
            device['resolutions'] = resolutions
            device['framerates'] = framerates

        return devices

    @staticmethod
    def list_audio_devices() -> list[dict]:
        """Enumerate ALSA audio input (capture) devices with capabilities.

        Calls arecord -l to list capture devices and parses the output.

        Returns:
            List of dicts with keys: device, name, formats, sample_rates, channels.
            Returns empty list if arecord is not installed.
        """
        try:
            result = subprocess.run(
                ['arecord', '-l'],
                capture_output=True, text=True, timeout=10
            )
        except FileNotFoundError:
            logger.error(
                "arecord not found. Install alsa-utils to enable audio device detection."
            )
            return []
        except subprocess.TimeoutExpired:
            logger.error("arecord -l timed out.")
            return []

        devices = DeviceDetector._parse_arecord_device_list(result.stdout)

        # Query each device for hw params
        for device in devices:
            formats, sample_rates, channels = DeviceDetector._query_audio_params(
                device['device']
            )
            device['formats'] = formats
            device['sample_rates'] = sample_rates
            device['channels'] = channels

        return devices

    @staticmethod
    def _parse_v4l2_device_list(output: str) -> list[dict]:
        """Parse v4l2-ctl --list-devices output into device entries.

        Example output:
            USB Camera (usb-0000:00:14.0-1):
                /dev/video0
                /dev/video1

            HD Webcam (usb-0000:00:14.0-2):
                /dev/video2
        """
        devices = []
        if not output or not output.strip():
            return devices

        current_name = None
        for line in output.splitlines():
            if not line.startswith('\t') and not line.startswith(' ') and line.strip():
                # This is a device name line (ends with colon typically)
                current_name = line.split('(')[0].strip().rstrip(':')
            elif line.strip().startswith('/dev/video'):
                path = line.strip()
                if current_name is not None:
                    devices.append({
                        'path': path,
                        'name': current_name,
                        'formats': [],
                        'resolutions': [],
                        'framerates': [],
                    })

        return devices

    @staticmethod
    def _query_v4l2_formats(device_path: str) -> tuple[list[str], list[str], list[int]]:
        """Query a V4L2 device for supported formats, resolutions, and frame rates.

        Calls v4l2-ctl --device=<path> --list-formats-ext and parses the output.

        Returns:
            Tuple of (formats, resolutions, framerates).
        """
        formats = []
        resolutions = []
        framerates = []

        try:
            result = subprocess.run(
                ['v4l2-ctl', f'--device={device_path}', '--list-formats-ext'],
                capture_output=True, text=True, timeout=10
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return formats, resolutions, framerates

        output = result.stdout
        if not output:
            return formats, resolutions, framerates

        # Parse pixel format names (e.g., 'MJPG', 'YUYV')
        # v4l2-ctl outputs lines like: [0]: 'MJPG' (Motion-JPEG, compressed)
        # or: Pixel Format: 'MJPG'
        for match in re.finditer(r"'(\w+)'", output):
            fmt = match.group(1)
            # Filter to only uppercase format codes (skip descriptions)
            if fmt.isupper() and len(fmt) >= 3 and fmt not in formats:
                formats.append(fmt)

        # Parse resolutions (e.g., 'Size: Discrete 640x480')
        for match in re.finditer(r'Size:\s*Discrete\s+(\d+x\d+)', output):
            res = match.group(1)
            if res not in resolutions:
                resolutions.append(res)

        # Parse frame rates (e.g., 'Interval: Discrete 0.033s (30.000 fps)')
        for match in re.finditer(r'\((\d+(?:\.\d+)?)\s*fps\)', output):
            fps = int(float(match.group(1)))
            if fps not in framerates:
                framerates.append(fps)

        framerates.sort()
        return formats, resolutions, framerates

    @staticmethod
    def _parse_arecord_device_list(output: str) -> list[dict]:
        """Parse arecord -l output into device entries.

        Example output:
            **** List of CAPTURE Hardware Devices ****
            card 1: Microphone [USB Microphone], device 0: USB Audio [USB Audio]
              Subdevices: 1/1
              Subdevice #0: subdevice #0
        """
        devices = []
        if not output or not output.strip():
            return devices

        # Match lines like: card 1: Microphone [USB Microphone], device 0: ...
        pattern = re.compile(
            r'card\s+(\d+):\s*\w+\s*\[([^\]]+)\],\s*device\s+(\d+):'
        )

        for match in pattern.finditer(output):
            card_num = match.group(1)
            name = match.group(2)
            device_num = match.group(3)
            hw_path = f"hw:{card_num},{device_num}"

            devices.append({
                'device': hw_path,
                'name': name,
                'formats': [],
                'sample_rates': [],
                'channels': [],
            })

        return devices

    @staticmethod
    def _query_audio_params(hw_device: str) -> tuple[list[str], list[int], list[int]]:
        """Query an ALSA device for supported formats, sample rates, and channels.

        Attempts to get hardware parameters using arecord --dump-hw-params.

        Returns:
            Tuple of (formats, sample_rates, channels).
        """
        formats = []
        sample_rates = []
        channels = []

        try:
            # arecord --dump-hw-params writes params to stderr then exits
            result = subprocess.run(
                ['arecord', '--dump-hw-params', '-D', hw_device,
                 '--duration=0', '/dev/null'],
                capture_output=True, text=True, timeout=5
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return formats, sample_rates, channels

        # Combine stdout and stderr since arecord may output to either
        output = result.stdout + '\n' + result.stderr

        # Parse FORMAT line (e.g., "FORMAT: S16_LE S32_LE")
        format_match = re.search(r'FORMAT:\s*(.+)', output)
        if format_match:
            fmt_str = format_match.group(1).strip()
            formats = [f.strip() for f in fmt_str.split() if f.strip()]

        # Parse RATE line (e.g., "RATE: [8000 48000]" or "RATE: 16000 44100 48000")
        rate_match = re.search(r'RATE:\s*(.+)', output)
        if rate_match:
            rate_str = rate_match.group(1).strip()
            # Handle range format [min max]
            range_match = re.match(r'\[(\d+)\s+(\d+)\]', rate_str)
            if range_match:
                min_rate = int(range_match.group(1))
                max_rate = int(range_match.group(2))
                # Report common rates within the range
                common_rates = [8000, 11025, 16000, 22050, 32000, 44100, 48000, 96000]
                sample_rates = [r for r in common_rates if min_rate <= r <= max_rate]
            else:
                # Individual rates listed
                for r in re.findall(r'\d+', rate_str):
                    rate = int(r)
                    if rate not in sample_rates:
                        sample_rates.append(rate)

        # Parse CHANNELS line (e.g., "CHANNELS: [1 2]" or "CHANNELS: 1 2")
        chan_match = re.search(r'CHANNELS:\s*(.+)', output)
        if chan_match:
            chan_str = chan_match.group(1).strip()
            range_match = re.match(r'\[(\d+)\s+(\d+)\]', chan_str)
            if range_match:
                min_ch = int(range_match.group(1))
                max_ch = int(range_match.group(2))
                channels = list(range(min_ch, max_ch + 1))
            else:
                for c in re.findall(r'\d+', chan_str):
                    ch = int(c)
                    if ch not in channels:
                        channels.append(ch)

        return formats, sample_rates, channels

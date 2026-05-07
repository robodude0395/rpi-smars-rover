"""Server configuration module for the SMARS Telepresence Rover."""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class ServerConfig:
    """Configuration dataclass for the unified rover server.

    Contains all hardware and network settings with sensible defaults
    for the Raspberry Pi Zero W deployment.
    """

    # Video settings
    video_device: int = 0
    video_resolution: Tuple[int, int] = (320, 240)
    video_fps: int = 15
    video_jpeg_quality: int = 50

    # Audio capture settings
    audio_input_device: Optional[int] = None  # None = system default
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_chunk_samples: int = 256  # 256 samples = 512 bytes at 16-bit

    # Audio playback settings
    audio_playback_device: str = 'default'
    audio_period_size: int = 128
    audio_max_periods: int = 2

    # SPI settings
    spi_bus: int = 0
    spi_device: int = 0
    spi_speed_hz: int = 500000
    spi_mode: int = 0

    # Server settings
    server_port: int = 8080
    server_host: str = '0.0.0.0'

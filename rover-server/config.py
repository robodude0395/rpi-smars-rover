"""Server configuration module for the SMARS Telepresence Rover."""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class ServerConfig:
    """Configuration dataclass for the unified rover server.

    Contains all hardware and network settings with defaults optimized
    for Raspberry Pi 5 (4-core ARM Cortex-A76).
    """

    # Video settings — Pi 5 can handle higher res and FPS comfortably
    video_device: int = 0
    video_resolution: Tuple[int, int] = (320, 240)
    video_fps: int = 30
    video_jpeg_quality: int = 50

    # Audio capture settings
    audio_input_device: Optional[int] = None  # None = system default
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_chunk_samples: int = 512  # 512 samples = 1024 bytes at 16-bit

    # Audio playback settings
    audio_playback_device: str = 'default'
    audio_period_size: int = 512
    audio_max_periods: int = 8

    # SPI settings
    spi_bus: int = 0
    spi_device: int = 0
    spi_speed_hz: int = 500000
    spi_mode: int = 0

    # Server settings
    server_port: int = 8080
    server_host: str = '0.0.0.0'

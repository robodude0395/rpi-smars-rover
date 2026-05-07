"""Video streaming module for the SMARS Telepresence Rover.

Provides MJPEG video capture and streaming using OpenCV VideoCapture.
Frames are captured from a V4L2 device, resized, JPEG-encoded, and
yielded as multipart HTTP chunks for Flask streaming responses.
"""

import logging
import threading
import time
from typing import Generator, Optional, Tuple

try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

logger = logging.getLogger(__name__)


class VideoStream:
    """Captures video from a V4L2 device and generates MJPEG frames.

    Thread-safe: stop() signals the generator to exit before releasing
    the capture device, preventing segfaults from concurrent access.

    Attributes:
        device: V4L2 device index (e.g., 0 for /dev/video0).
        resolution: Target frame size as (width, height).
        fps: Target frames per second.
        jpeg_quality: JPEG encoding quality (0-100).
    """

    def __init__(self, device: int = 0, resolution: Tuple[int, int] = (320, 240),
                 fps: int = 15, jpeg_quality: int = 50):
        """Initialize video capture parameters.

        Args:
            device: V4L2 device index.
            resolution: Target resolution as (width, height).
            fps: Target frame rate.
            jpeg_quality: JPEG encoding quality (0-100).
        """
        self.device = device
        self.resolution = resolution
        self.fps = fps
        self.jpeg_quality = jpeg_quality
        self._capture: Optional[object] = None
        self._active = False
        self._lock = threading.Lock()
        self._generating = False

    def start(self):
        """Open the video device.

        Sets is_active to True on success, False on failure.
        Logs an error if the camera cannot be opened.
        """
        if not _CV2_AVAILABLE:
            logger.error("OpenCV (cv2) is not available. Video streaming disabled.")
            self._active = False
            return

        with self._lock:
            self._capture = cv2.VideoCapture(self.device)
            if not self._capture.isOpened():
                logger.error(
                    "Failed to open video device %d. Video streaming disabled.",
                    self.device
                )
                self._capture = None
                self._active = False
                return

            self._active = True
            logger.info(
                "Video stream started: device=%d, resolution=%s, fps=%d, quality=%d",
                self.device, self.resolution, self.fps, self.jpeg_quality
            )

    def stop(self):
        """Release the video device and stop streaming.

        Signals the generator to stop, waits for it to exit, then releases
        the capture device safely.
        """
        # Signal generator to stop
        self._active = False

        # Wait for generator to finish using the capture device
        deadline = time.time() + 2.0
        while self._generating and time.time() < deadline:
            time.sleep(0.05)

        # Now safe to release
        with self._lock:
            if self._capture is not None:
                self._capture.release()
                self._capture = None

        logger.info("Video stream stopped.")

    def generate_frames(self) -> Generator[bytes, None, None]:
        """Yield MJPEG frames as multipart HTTP chunks.

        Each yielded chunk is formatted as:
            b'--frame\\r\\nContent-Type: image/jpeg\\r\\n\\r\\n' + jpeg_bytes + b'\\r\\n'

        Maintains frame pacing based on the configured FPS. Uses adaptive timing
        that accounts for actual capture and encoding duration.

        Yields:
            bytes: Multipart-formatted JPEG frame data.
        """
        if not self._active or self._capture is None:
            return

        self._generating = True
        frame_interval = 1.0 / self.fps
        next_frame_time = time.time()

        try:
            while self._active:
                now = time.time()

                # If we're behind schedule, skip the sleep and catch up
                if now < next_frame_time:
                    time.sleep(next_frame_time - now)

                next_frame_time = time.time() + frame_interval

                # Check again after sleep in case stop() was called
                if not self._active:
                    break

                with self._lock:
                    if self._capture is None:
                        break
                    ret, frame = self._capture.read()

                if not ret:
                    logger.debug("Frame capture failed, skipping frame.")
                    continue

                # Resize to configured resolution
                frame = cv2.resize(frame, self.resolution)

                # Encode as JPEG with configured quality
                encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
                ret, jpeg = cv2.imencode('.jpg', frame, encode_params)
                if not ret:
                    logger.debug("JPEG encoding failed, skipping frame.")
                    continue

                jpeg_bytes = jpeg.tobytes()

                # Yield as multipart frame
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' +
                    jpeg_bytes +
                    b'\r\n'
                )
        finally:
            self._generating = False

    @property
    def is_active(self) -> bool:
        """Whether video capture is currently running."""
        return self._active

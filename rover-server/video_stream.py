"""Video streaming module for the SMARS Telepresence Rover.

Provides MJPEG video capture and streaming using OpenCV VideoCapture.
Frames are captured in a dedicated background thread to avoid blocking
gevent's event loop (which handles motor commands and audio).

The capture thread continuously grabs frames and stores the latest one.
The generator yields frames from this buffer, ensuring motor/audio
Socket.IO events are never blocked by camera I/O.
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

try:
    from gevent import sleep as gevent_sleep
    _GEVENT_AVAILABLE = True
except ImportError:
    _GEVENT_AVAILABLE = False
    gevent_sleep = time.sleep

logger = logging.getLogger(__name__)


class VideoStream:
    """Captures video from a V4L2 device and generates MJPEG frames.

    Uses a dedicated capture thread so that the blocking cv2.read() call
    doesn't starve gevent's event loop. The generator yields the latest
    JPEG-encoded frame at the configured FPS.

    Attributes:
        device: V4L2 device index (e.g., 0 for /dev/video0).
        resolution: Target frame size as (width, height).
        fps: Target frames per second.
        jpeg_quality: JPEG encoding quality (0-100).
    """

    def __init__(self, device: int = 0, resolution: Tuple[int, int] = (320, 240),
                 fps: int = 30, jpeg_quality: int = 50):
        self.device = device
        self.resolution = resolution
        self.fps = fps
        self.jpeg_quality = jpeg_quality
        self._capture: Optional[object] = None
        self._active = False
        self._lock = threading.Lock()
        self._generating = False

        # Background capture thread state
        self._capture_thread: Optional[threading.Thread] = None
        self._latest_frame: Optional[bytes] = None
        self._frame_event = threading.Event()

    def start(self):
        """Open the video device and start the background capture thread."""
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

            # Set camera properties
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            self._capture.set(cv2.CAP_PROP_FPS, self.fps)
            self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            self._active = True

        # Start background capture thread
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            name="VideoCaptureThread",
            daemon=True
        )
        self._capture_thread.start()

        logger.info(
            "Video stream started: device=%d, resolution=%s, fps=%d, quality=%d",
            self.device, self.resolution, self.fps, self.jpeg_quality
        )

    def stop(self):
        """Stop the capture thread and release the video device."""
        self._active = False

        # Wait for capture thread to finish
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=2.0)
            self._capture_thread = None

        # Wait for generator to finish
        deadline = time.time() + 2.0
        while self._generating and time.time() < deadline:
            time.sleep(0.05)

        # Release camera
        with self._lock:
            if self._capture is not None:
                self._capture.release()
                self._capture = None

        self._latest_frame = None
        logger.info("Video stream stopped.")

    def _capture_loop(self):
        """Background thread: continuously captures and encodes frames.

        Runs in a real OS thread so cv2.read() blocking doesn't affect
        gevent's event loop. Stores the latest JPEG-encoded frame for
        the generator to pick up.
        """
        frame_interval = 1.0 / self.fps
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]

        while self._active:
            frame_start = time.time()

            with self._lock:
                if self._capture is None:
                    break
                ret, frame = self._capture.read()

            if not ret:
                time.sleep(0.01)
                continue

            # Resize to configured resolution
            frame = cv2.resize(frame, self.resolution)

            # Encode as JPEG
            ret, jpeg = cv2.imencode('.jpg', frame, encode_params)
            if not ret:
                continue

            # Store latest frame and signal the generator
            self._latest_frame = jpeg.tobytes()
            self._frame_event.set()

            # Frame pacing
            elapsed = time.time() - frame_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def generate_frames(self) -> Generator[bytes, None, None]:
        """Yield MJPEG frames as multipart HTTP chunks.

        This runs in gevent's event loop. It does NOT block on camera I/O —
        it simply picks up the latest frame from the capture thread and yields it.
        Between frames, it uses gevent_sleep() to yield control to other greenlets
        (motor commands, audio, etc).

        Yields:
            bytes: Multipart-formatted JPEG frame data.
        """
        if not self._active:
            return

        self._generating = True
        frame_interval = 1.0 / self.fps

        try:
            while self._active:
                # Wait for a new frame (with timeout so we can check _active)
                self._frame_event.wait(timeout=0.1)
                self._frame_event.clear()

                if not self._active:
                    break

                jpeg_bytes = self._latest_frame
                if jpeg_bytes is None:
                    gevent_sleep(0.01)
                    continue

                # Yield as multipart frame
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' +
                    jpeg_bytes +
                    b'\r\n'
                )

                # Yield control to gevent event loop for motor/audio processing
                gevent_sleep(frame_interval)
        finally:
            self._generating = False

    @property
    def is_active(self) -> bool:
        """Whether video capture is currently running."""
        return self._active

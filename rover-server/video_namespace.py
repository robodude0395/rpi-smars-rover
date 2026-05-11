"""Socket.IO /video namespace handler for MJPEG frame streaming.

Streams JPEG frames from the rover's camera to connected clients over
the existing Socket.IO connection, bypassing WebKit's restrictions on
cross-origin HTTP image loads.
"""

import logging
import threading
import time

from flask_socketio import Namespace

logger = logging.getLogger(__name__)


class VideoNamespace(Namespace):
    """Socket.IO namespace for video streaming at /video.

    Captures frames from OpenCV and emits them as binary JPEG data.
    Starts/stops the capture thread based on client connections.
    """

    def __init__(self, namespace, socketio, config_dict):
        super().__init__(namespace)
        self._socketio = socketio
        self._config = config_dict
        self._connected_clients = 0
        self._streaming = False
        self._thread = None
        self._lock = threading.Lock()

    def on_connect(self):
        self._connected_clients += 1
        logger.info("Client connected to /video (total: %d)", self._connected_clients)

        if self._connected_clients == 1 and not self._streaming:
            self._start_streaming()

    def on_disconnect(self):
        self._connected_clients = max(0, self._connected_clients - 1)
        logger.info("Client disconnected from /video (total: %d)", self._connected_clients)

        if self._connected_clients == 0:
            self._stop_streaming()

    def on_request_frame(self, data=None):
        """Client can request settings update via this event if needed."""
        pass

    def _start_streaming(self):
        self._streaming = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _stop_streaming(self):
        self._streaming = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def _capture_loop(self):
        try:
            import cv2
        except ImportError:
            logger.error("OpenCV not available for video namespace")
            self._streaming = False
            return

        resolution = tuple(self._config['video_resolution'])
        fps = self._config['video_fps']
        jpeg_quality = self._config['video_jpeg_quality']
        device = self._config['video_device']

        cap = cv2.VideoCapture(device)
        if not cap.isOpened():
            logger.error("Video namespace: failed to open camera device %d", device)
            self._streaming = False
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
        cap.set(cv2.CAP_PROP_FPS, fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        logger.info("Video namespace: camera opened at %s %dfps", resolution, fps)

        frame_interval = 1.0 / fps
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]

        while self._streaming and self._connected_clients > 0:
            start = time.time()

            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            frame = cv2.resize(frame, resolution)
            ret, jpeg = cv2.imencode('.jpg', frame, encode_params)
            if not ret:
                continue

            try:
                self._socketio.emit('frame', jpeg.tobytes(), namespace=self.namespace)
            except Exception as e:
                logger.warning("Failed to emit video frame: %s", e)
                break

            elapsed = time.time() - start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        cap.release()
        self._streaming = False
        logger.info("Video namespace: capture stopped")

"""Main entry point for the SMARS Telepresence Rover server.

Multiprocess architecture for the Raspberry Pi 3B+ (4 cores):
- Process 1: UDP motor control (port 8082) — raw UDP → SPI, zero latency
- Process 2: MJPEG video server (port 8081) — OpenCV capture + streaming
- Process 3 (main): Flask-SocketIO (port 8080) — audio + settings API

Each process runs on its own core. Motor commands bypass all web frameworks.
"""

import logging
import multiprocessing
import signal
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')
logger = logging.getLogger(__name__)


def run_video_server(config_dict):
    """Run the MJPEG video server in a separate process (port 8081)."""
    import time
    from flask import Flask, Response, jsonify, request

    try:
        import cv2
    except ImportError:
        logger.error("OpenCV not available in video process")
        return

    app = Flask(__name__)

    capture = None
    resolution = tuple(config_dict['video_resolution'])
    fps = config_dict['video_fps']
    jpeg_quality = config_dict['video_jpeg_quality']
    device = config_dict['video_device']

    def open_camera():
        nonlocal capture
        capture = cv2.VideoCapture(device)
        if capture.isOpened():
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
            capture.set(cv2.CAP_PROP_FPS, fps)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            logger.info("Video: camera opened at %s %dfps", resolution, fps)
        else:
            logger.error("Video: failed to open camera device %d", device)
            capture = None

    def generate_frames():
        frame_interval = 1.0 / fps
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]

        while True:
            if capture is None or not capture.isOpened():
                time.sleep(0.1)
                continue

            start = time.time()
            ret, frame = capture.read()
            if not ret:
                time.sleep(0.01)
                continue

            frame = cv2.resize(frame, resolution)
            ret, jpeg = cv2.imencode('.jpg', frame, encode_params)
            if not ret:
                continue

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                jpeg.tobytes() +
                b'\r\n'
            )

            elapsed = time.time() - start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    @app.after_request
    def cors(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    @app.route('/video_feed')
    def video_feed():
        if capture is None or not capture.isOpened():
            return jsonify({'error': 'Video device unavailable'}), 503
        return Response(
            generate_frames(),
            mimetype='multipart/x-mixed-replace; boundary=frame'
        )

    @app.route('/video/config', methods=['POST', 'OPTIONS'])
    def update_video_config():
        if request.method == 'OPTIONS':
            return '', 204
        nonlocal resolution, fps, jpeg_quality, capture
        data = request.get_json(silent=True) or {}

        if 'resolution' in data:
            resolution = tuple(data['resolution'])
        if 'fps' in data:
            fps = max(1, min(30, int(data['fps'])))
        if 'jpeg_quality' in data:
            jpeg_quality = max(10, min(95, int(data['jpeg_quality'])))

        if capture is not None:
            capture.release()
        time.sleep(0.5)
        open_camera()

        return jsonify({'status': 'ok', 'resolution': list(resolution), 'fps': fps})

    open_camera()
    app.run(host='0.0.0.0', port=8081, threaded=True)


def run_control_server(config_dict):
    """Run the Flask-SocketIO server for audio + settings (port 8080)."""
    from flask import Flask, jsonify
    from flask_socketio import SocketIO

    from audio_capture import AudioCapture
    from audio_in_namespace import AudioInNamespace
    from audio_out_namespace import AudioOutNamespace
    from audio_playback import AudioPlayback
    from config import ServerConfig
    from control_namespace import ControlNamespace
    from device_detector import DeviceDetector

    config = ServerConfig()

    app = Flask(__name__)
    socketio = SocketIO(app, async_mode='threading', cors_allowed_origins='*')

    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    # Audio components
    audio_capture = AudioCapture(
        device_index=config.audio_input_device,
        sample_rate=config.audio_sample_rate,
        chunk_size=config.audio_chunk_samples,
    )

    audio_playback = AudioPlayback(
        device=config.audio_playback_device,
        sample_rate=config.audio_sample_rate,
        period_size=config.audio_period_size,
        max_periods=config.audio_max_periods,
    )

    # Register audio + control namespaces
    socketio.on_namespace(ControlNamespace('/control'))
    socketio.on_namespace(AudioOutNamespace('/audio_out', audio_capture, socketio))
    socketio.on_namespace(AudioInNamespace('/audio_in', audio_playback))

    # Simple API routes
    @app.route('/api/devices', methods=['GET'])
    def get_devices():
        try:
            video_devices = DeviceDetector.list_video_devices()
            audio_devices = DeviceDetector.list_audio_devices()
        except Exception as e:
            logger.warning("Device detection failed: %s", e)
            video_devices = []
            audio_devices = []
        return jsonify({"video": video_devices, "audio": audio_devices})

    @app.route('/api/stream/status', methods=['GET'])
    def stream_status():
        return jsonify({
            "video": {"active": True, "port": 8081},
            "motor": {"active": True, "port": 8082, "protocol": "udp"},
            "audio_capture": {"active": audio_capture.is_active},
        })

    socketio.run(app, host=config.server_host, port=config.server_port)


if __name__ == '__main__':
    from config import ServerConfig
    config = ServerConfig()

    config_dict = {
        'video_device': config.video_device,
        'video_resolution': list(config.video_resolution),
        'video_fps': config.video_fps,
        'video_jpeg_quality': config.video_jpeg_quality,
    }

    # Process 1: UDP motor control (port 8082)
    motor_process = multiprocessing.Process(
        target=lambda: __import__('motor_udp').run_motor_server(
            config.spi_bus, config.spi_device, config.spi_speed_hz
        ),
        name="MotorUDP",
        daemon=True
    )
    motor_process.start()
    logger.info("Motor UDP server started (port 8082, PID %d)", motor_process.pid)

    # Process 2: Video server (port 8081)
    video_process = multiprocessing.Process(
        target=run_video_server,
        args=(config_dict,),
        name="VideoServer",
        daemon=True
    )
    video_process.start()
    logger.info("Video server started (port 8081, PID %d)", video_process.pid)

    # Handle graceful shutdown
    def shutdown(sig, frame):
        logger.info("Shutting down...")
        motor_process.terminate()
        video_process.terminate()
        motor_process.join(timeout=2)
        video_process.join(timeout=2)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Process 3 (main): Audio + settings server (port 8080)
    logger.info("Control server starting (port 8080)...")
    run_control_server(config_dict)

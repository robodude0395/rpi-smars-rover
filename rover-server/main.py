"""Main entry point for the SMARS Telepresence Rover server.

Multiprocess architecture for the Raspberry Pi 3B+ (4 cores):
- Process 1 (main): Flask-SocketIO for motor control + audio (instant response)
- Process 2: MJPEG video capture and HTTP streaming (CPU-intensive, isolated)

Each process runs on its own core, so video encoding never blocks motor commands.
"""

import logging
import multiprocessing
import signal
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')
logger = logging.getLogger(__name__)


def run_video_server(config_dict):
    """Run the MJPEG video server in a separate process.

    Serves video on port 8081. Completely independent from the control server.
    """
    import time
    from flask import Flask, Response, jsonify, request

    try:
        import cv2
    except ImportError:
        logger.error("OpenCV not available in video process")
        return

    app = Flask(__name__)

    # Video capture state
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
        return response

    @app.route('/video_feed')
    def video_feed():
        if capture is None or not capture.isOpened():
            return jsonify({'error': 'Video device unavailable'}), 503
        return Response(
            generate_frames(),
            mimetype='multipart/x-mixed-replace; boundary=frame'
        )

    @app.route('/video/config', methods=['POST'])
    def update_video_config():
        """Update video settings and restart camera."""
        nonlocal resolution, fps, jpeg_quality, capture
        data = request.get_json(silent=True) or {}

        if 'resolution' in data:
            resolution = tuple(data['resolution'])
        if 'fps' in data:
            fps = max(1, min(30, int(data['fps'])))
        if 'jpeg_quality' in data:
            jpeg_quality = max(10, min(95, int(data['jpeg_quality'])))

        # Restart camera with new settings
        if capture is not None:
            capture.release()
        open_camera()

        return jsonify({'status': 'ok', 'resolution': list(resolution), 'fps': fps})

    open_camera()
    app.run(host='0.0.0.0', port=8081, threaded=True)


def run_control_server(config_dict):
    """Run the Socket.IO control server (motor + audio) in the main process.

    Serves on port 8080. Handles motor commands, audio streaming, and API.
    Uses threading async mode for simplicity — no heavy CPU work here.
    """
    from flask import Flask, Response, jsonify
    from flask_socketio import SocketIO

    from api_routes import api_blueprint, init_api_routes
    from audio_capture import AudioCapture
    from audio_in_namespace import AudioInNamespace
    from audio_out_namespace import AudioOutNamespace
    from audio_playback import AudioPlayback
    from config import ServerConfig
    from control_namespace import ControlNamespace
    from motor_controller import RoverController

    config = ServerConfig()

    app = Flask(__name__)
    socketio = SocketIO(app, async_mode='threading', cors_allowed_origins='*')

    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    # Initialize hardware
    rover_controller = RoverController(
        bus=config.spi_bus,
        device=config.spi_device,
        speed_hz=config.spi_speed_hz,
    )

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

    # Register namespaces
    socketio.on_namespace(ControlNamespace('/control', rover_controller))
    socketio.on_namespace(AudioOutNamespace('/audio_out', audio_capture, socketio))
    socketio.on_namespace(AudioInNamespace('/audio_in', audio_playback))

    # Stub video stream for API compatibility
    class VideoStub:
        is_active = True
        def start(self): pass
        def stop(self): pass

    video_stub = VideoStub()
    init_api_routes(video_stub, audio_capture, audio_playback, config, rover_controller)
    app.register_blueprint(api_blueprint, url_prefix='/api')

    # Proxy video config changes to the video process
    @app.route('/video_feed')
    def video_feed():
        """Redirect to the video server on port 8081."""
        from flask import redirect
        return redirect('http://' + config.server_host + ':8081/video_feed', code=302)

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

    # Start video server in separate process (runs on its own core)
    video_process = multiprocessing.Process(
        target=run_video_server,
        args=(config_dict,),
        name="VideoServer",
        daemon=True
    )
    video_process.start()
    logger.info("Video server started on port 8081 (PID %d)", video_process.pid)

    # Handle graceful shutdown
    def shutdown(sig, frame):
        logger.info("Shutting down...")
        video_process.terminate()
        video_process.join(timeout=3)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Run control server in main process
    logger.info("Control server starting on port 8080...")
    run_control_server(config_dict)

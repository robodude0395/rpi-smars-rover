"""Main entry point for the SMARS Telepresence Rover server.

Integrates all components into a single Flask-SocketIO application:
- /control namespace for motor commands via SPI
- /audio_out namespace for rover mic → client streaming
- /audio_in namespace for client mic → rover speaker
- /video_feed HTTP endpoint for MJPEG video streaming

Uses gevent for async I/O, allowing concurrent handling of video streaming,
audio, and motor commands across multiple cores without GIL contention.
"""

from gevent import monkey
monkey.patch_all()

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
from video_stream import VideoStream

# Load configuration
config = ServerConfig()

# Create Flask app and SocketIO instance
# gevent async mode: true cooperative concurrency, no GIL blocking
app = Flask(__name__)
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins='*')


@app.after_request
def add_cors_headers(response):
    """Add CORS headers to all responses."""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# Initialize hardware interfaces
rover_controller = RoverController(
    bus=config.spi_bus,
    device=config.spi_device,
    speed_hz=config.spi_speed_hz,
)

video_stream = VideoStream(
    device=config.video_device,
    resolution=config.video_resolution,
    fps=config.video_fps,
    jpeg_quality=config.video_jpeg_quality,
)
video_stream.start()

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

# Register WebSocket namespaces
socketio.on_namespace(ControlNamespace('/control', rover_controller))
socketio.on_namespace(AudioOutNamespace('/audio_out', audio_capture, socketio))
socketio.on_namespace(AudioInNamespace('/audio_in', audio_playback))

# Register REST API blueprint
init_api_routes(video_stream, audio_capture, audio_playback, config, rover_controller)
app.register_blueprint(api_blueprint, url_prefix='/api')


# HTTP routes
@app.route('/video_feed')
def video_feed():
    """MJPEG video streaming endpoint.

    Returns a streaming response with multipart JPEG frames from the
    video capture device. Returns HTTP 503 if the video device is unavailable.
    """
    if not video_stream.is_active:
        return jsonify({'error': 'Video device unavailable'}), 503
    return Response(
        video_stream.generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


# Flask error handlers
@app.errorhandler(404)
def not_found(e):
    """Handle 404 Not Found errors."""
    return jsonify({'error': 'Not found', 'message': str(e)}), 404


@app.errorhandler(500)
def internal_error(e):
    """Handle 500 Internal Server Error."""
    return jsonify({'error': 'Internal server error', 'message': str(e)}), 500


if __name__ == '__main__':
    socketio.run(
        app,
        host=config.server_host,
        port=config.server_port,
    )

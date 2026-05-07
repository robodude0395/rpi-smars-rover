"""Socket.IO /control namespace handler for motor commands.

Handles incoming motor command messages from the desktop client,
validates them, forwards to the RoverController via SPI, and
sends acknowledgments back to the client.
"""

import logging

from flask_socketio import Namespace, emit

logger = logging.getLogger(__name__)


class ControlNamespace(Namespace):
    """Socket.IO namespace for motor control at /control.

    Validates incoming motor command messages, dispatches them to the
    RoverController, and emits acknowledgments or errors back to the client.
    On client disconnect, sends a stop command to prevent runaway motors.
    """

    def __init__(self, namespace, rover_controller):
        """Initialize the control namespace.

        Args:
            namespace: The Socket.IO namespace path (e.g., '/control').
            rover_controller: A RoverController instance for SPI motor commands.
        """
        super().__init__(namespace)
        self.rover_controller = rover_controller

    def on_connect(self):
        """Handle client connection to /control namespace."""
        logger.info("Client connected to /control namespace")

    def on_ping_latency(self, data):
        """Handle latency ping — echo back immediately for round-trip measurement."""
        emit('pong_latency', data)

    def on_disconnect(self):
        """Handle client disconnect — send stop command to prevent runaway motors."""
        logger.info("Client disconnected from /control namespace, sending stop command")
        self.rover_controller.stop()

    def on_command(self, data):
        """Handle incoming motor command messages.

        Validates the message format and dispatches to the motor controller.
        Emits an 'ack' event on success or an 'error' event on validation failure.

        Expected message format:
            {"type": "motor", "left": int, "right": int, "seq": int}

        Args:
            data: The message payload (should be a dict).
        """
        # Fast path: minimal validation for motor commands
        if not isinstance(data, dict):
            emit('error', {'message': 'Invalid message format'})
            return

        cmd_type = data.get('type')
        seq = data.get('seq', 0)

        if cmd_type != 'motor':
            emit('error', {'message': f'Unknown command type: {cmd_type}'})
            return

        left = data.get('left')
        right = data.get('right')

        if left is None or right is None:
            emit('error', {'message': 'Missing left/right fields'})
            return

        left_int = int(left)
        right_int = int(right)

        # Log motor commands for debugging
        if left_int != 0 or right_int != 0:
            print(f"Motor: L={left_int} R={right_int}")

        # Send to motor controller
        self.rover_controller.send_command(left_int, right_int)

        # Emit lightweight acknowledgment
        emit('ack', {'seq': int(seq)})

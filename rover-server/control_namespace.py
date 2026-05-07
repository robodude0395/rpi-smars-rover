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
        # Validate that data is a dict
        if not isinstance(data, dict):
            emit('error', {'message': 'Invalid message format: expected a JSON object'})
            return

        # Validate required fields exist
        required_fields = ['type', 'left', 'right', 'seq']
        missing_fields = [f for f in required_fields if f not in data]
        if missing_fields:
            emit('error', {
                'message': f'Missing required fields: {", ".join(missing_fields)}'
            })
            return

        # Validate field types
        if data['type'] != 'motor':
            emit('error', {'message': f'Unknown command type: {data["type"]}'})
            return

        if not isinstance(data['left'], (int, float)):
            emit('error', {'message': 'Field "left" must be a number'})
            return

        if not isinstance(data['right'], (int, float)):
            emit('error', {'message': 'Field "right" must be a number'})
            return

        if not isinstance(data['seq'], (int, float)):
            emit('error', {'message': 'Field "seq" must be a number'})
            return

        # Convert to int (handles float values sent from JS)
        left = int(data['left'])
        right = int(data['right'])
        seq = int(data['seq'])

        # Send command to motor controller
        self.rover_controller.send_command(left, right)

        # Emit acknowledgment with matching sequence number
        emit('ack', {'type': 'ack', 'seq': seq})

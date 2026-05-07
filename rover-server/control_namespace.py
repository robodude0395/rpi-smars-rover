"""Socket.IO /control namespace handler for motor commands.

Receives motor commands from the client via Socket.IO and forwards them
to the UDP motor process via localhost UDP. This keeps the SPI communication
in its own dedicated process while maintaining browser compatibility.
"""

import logging
import socket
import struct

from flask_socketio import Namespace, emit

logger = logging.getLogger(__name__)

# UDP socket for forwarding motor commands to the motor process
_motor_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_MOTOR_ADDR = ('127.0.0.1', 8082)


class ControlNamespace(Namespace):
    """Socket.IO namespace for motor control at /control.

    Receives motor commands and forwards them via UDP to the motor process.
    Also handles latency pings and disconnect safety stops.
    """

    def __init__(self, namespace):
        super().__init__(namespace)
        self._seq = 0

    def on_connect(self):
        logger.info("Client connected to /control namespace")

    def on_ping_latency(self, data):
        """Echo back for latency measurement."""
        emit('pong_latency', data)

    def on_disconnect(self):
        """Send stop command on disconnect to prevent runaway motors."""
        logger.info("Client disconnected from /control, sending stop")
        self._send_udp(128, 128)

    def on_command(self, data):
        """Handle motor command — forward to UDP motor process.

        Expected: {"type": "motor", "left": int, "right": int, "seq": int}
        """
        if not isinstance(data, dict):
            return

        if data.get('type') != 'motor':
            return

        left = data.get('left', 0)
        right = data.get('right', 0)

        # Convert signed (-127..127) to offset byte (1..255)
        left_byte = max(1, min(255, int(left) + 128))
        right_byte = max(1, min(255, int(right) + 128))

        print(f"CMD: L={left} R={right} -> bytes [{left_byte}, {right_byte}]")
        self._send_udp(left_byte, right_byte)

    def _send_udp(self, left_byte, right_byte):
        """Send a 4-byte UDP packet to the motor process."""
        self._seq = (self._seq + 1) % 256
        packet = bytes([0xAA, left_byte, right_byte, self._seq])
        try:
            _motor_sock.sendto(packet, _MOTOR_ADDR)
        except OSError:
            pass

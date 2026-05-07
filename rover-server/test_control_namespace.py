"""Unit tests for control_namespace.py — /control WebSocket namespace."""

import sys
import unittest
from unittest.mock import MagicMock, patch

# Mock spidev before importing anything that touches motor_controller
mock_spidev = MagicMock()
sys.modules['spidev'] = mock_spidev

import importlib
import motor_controller
importlib.reload(motor_controller)

from flask import Flask
from flask_socketio import SocketIO

from control_namespace import ControlNamespace
from motor_controller import RoverController


class TestControlNamespace(unittest.TestCase):
    """Tests for the /control Socket.IO namespace."""

    def setUp(self):
        """Set up Flask test app with SocketIO and a mocked RoverController."""
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True

        self.mock_controller = MagicMock(spec=RoverController)
        self.mock_controller.send_command.return_value = True
        self.mock_controller.stop.return_value = True

        self.socketio = SocketIO(self.app, async_mode='threading')
        self.socketio.on_namespace(
            ControlNamespace('/control', self.mock_controller)
        )

        self.client = self.socketio.test_client(
            self.app, namespace='/control'
        )

    def tearDown(self):
        """Disconnect the test client."""
        if self.client.is_connected(namespace='/control'):
            self.client.disconnect(namespace='/control')

    def test_connect(self):
        """Client can connect to /control namespace."""
        assert self.client.is_connected(namespace='/control')

    def test_valid_motor_command_calls_send_command(self):
        """Valid motor command calls RoverController.send_command with correct values."""
        self.client.emit('command', {
            'type': 'motor',
            'left': 100,
            'right': -50,
            'seq': 1
        }, namespace='/control')

        self.mock_controller.send_command.assert_called_once_with(100, -50)

    def test_valid_motor_command_emits_ack(self):
        """Valid motor command emits ack with matching seq number."""
        self.client.emit('command', {
            'type': 'motor',
            'left': 127,
            'right': 127,
            'seq': 42
        }, namespace='/control')

        received = self.client.get_received(namespace='/control')
        ack_messages = [m for m in received if m['name'] == 'ack']
        assert len(ack_messages) == 1
        assert ack_messages[0]['args'][0] == {'type': 'ack', 'seq': 42}

    def test_missing_type_field_emits_error(self):
        """Missing 'type' field emits error event."""
        self.client.emit('command', {
            'left': 100,
            'right': 100,
            'seq': 1
        }, namespace='/control')

        received = self.client.get_received(namespace='/control')
        error_messages = [m for m in received if m['name'] == 'error']
        assert len(error_messages) == 1
        assert 'type' in error_messages[0]['args'][0]['message']
        self.mock_controller.send_command.assert_not_called()

    def test_missing_left_field_emits_error(self):
        """Missing 'left' field emits error event."""
        self.client.emit('command', {
            'type': 'motor',
            'right': 100,
            'seq': 1
        }, namespace='/control')

        received = self.client.get_received(namespace='/control')
        error_messages = [m for m in received if m['name'] == 'error']
        assert len(error_messages) == 1
        assert 'left' in error_messages[0]['args'][0]['message']

    def test_missing_right_field_emits_error(self):
        """Missing 'right' field emits error event."""
        self.client.emit('command', {
            'type': 'motor',
            'left': 100,
            'seq': 1
        }, namespace='/control')

        received = self.client.get_received(namespace='/control')
        error_messages = [m for m in received if m['name'] == 'error']
        assert len(error_messages) == 1
        assert 'right' in error_messages[0]['args'][0]['message']

    def test_missing_seq_field_emits_error(self):
        """Missing 'seq' field emits error event."""
        self.client.emit('command', {
            'type': 'motor',
            'left': 100,
            'right': 100
        }, namespace='/control')

        received = self.client.get_received(namespace='/control')
        error_messages = [m for m in received if m['name'] == 'error']
        assert len(error_messages) == 1
        assert 'seq' in error_messages[0]['args'][0]['message']

    def test_missing_multiple_fields_emits_error(self):
        """Missing multiple fields lists all missing in error."""
        self.client.emit('command', {
            'type': 'motor'
        }, namespace='/control')

        received = self.client.get_received(namespace='/control')
        error_messages = [m for m in received if m['name'] == 'error']
        assert len(error_messages) == 1
        msg = error_messages[0]['args'][0]['message']
        assert 'left' in msg
        assert 'right' in msg
        assert 'seq' in msg

    def test_invalid_type_value_emits_error(self):
        """Unknown command type emits error event."""
        self.client.emit('command', {
            'type': 'unknown',
            'left': 100,
            'right': 100,
            'seq': 1
        }, namespace='/control')

        received = self.client.get_received(namespace='/control')
        error_messages = [m for m in received if m['name'] == 'error']
        assert len(error_messages) == 1
        assert 'Unknown command type' in error_messages[0]['args'][0]['message']
        self.mock_controller.send_command.assert_not_called()

    def test_non_dict_message_emits_error(self):
        """Non-dict message emits error event."""
        self.client.emit('command', 'not a dict', namespace='/control')

        received = self.client.get_received(namespace='/control')
        error_messages = [m for m in received if m['name'] == 'error']
        assert len(error_messages) == 1
        assert 'Invalid message format' in error_messages[0]['args'][0]['message']

    def test_non_numeric_left_emits_error(self):
        """Non-numeric 'left' field emits error event."""
        self.client.emit('command', {
            'type': 'motor',
            'left': 'fast',
            'right': 100,
            'seq': 1
        }, namespace='/control')

        received = self.client.get_received(namespace='/control')
        error_messages = [m for m in received if m['name'] == 'error']
        assert len(error_messages) == 1
        assert 'left' in error_messages[0]['args'][0]['message']

    def test_non_numeric_right_emits_error(self):
        """Non-numeric 'right' field emits error event."""
        self.client.emit('command', {
            'type': 'motor',
            'left': 100,
            'right': 'slow',
            'seq': 1
        }, namespace='/control')

        received = self.client.get_received(namespace='/control')
        error_messages = [m for m in received if m['name'] == 'error']
        assert len(error_messages) == 1
        assert 'right' in error_messages[0]['args'][0]['message']

    def test_non_numeric_seq_emits_error(self):
        """Non-numeric 'seq' field emits error event."""
        self.client.emit('command', {
            'type': 'motor',
            'left': 100,
            'right': 100,
            'seq': 'abc'
        }, namespace='/control')

        received = self.client.get_received(namespace='/control')
        error_messages = [m for m in received if m['name'] == 'error']
        assert len(error_messages) == 1
        assert 'seq' in error_messages[0]['args'][0]['message']

    def test_float_values_accepted_and_converted(self):
        """Float values for left/right/seq are accepted and converted to int."""
        self.client.emit('command', {
            'type': 'motor',
            'left': 50.7,
            'right': -30.2,
            'seq': 5.0
        }, namespace='/control')

        self.mock_controller.send_command.assert_called_once_with(50, -30)
        received = self.client.get_received(namespace='/control')
        ack_messages = [m for m in received if m['name'] == 'ack']
        assert len(ack_messages) == 1
        assert ack_messages[0]['args'][0] == {'type': 'ack', 'seq': 5}

    def test_disconnect_sends_stop_command(self):
        """Disconnecting from /control sends stop command via SPI."""
        self.client.disconnect(namespace='/control')

        self.mock_controller.stop.assert_called_once()

    def test_zero_speed_command(self):
        """Stop command (left=0, right=0) is handled correctly."""
        self.client.emit('command', {
            'type': 'motor',
            'left': 0,
            'right': 0,
            'seq': 99
        }, namespace='/control')

        self.mock_controller.send_command.assert_called_once_with(0, 0)
        received = self.client.get_received(namespace='/control')
        ack_messages = [m for m in received if m['name'] == 'ack']
        assert len(ack_messages) == 1
        assert ack_messages[0]['args'][0] == {'type': 'ack', 'seq': 99}


if __name__ == '__main__':
    unittest.main()

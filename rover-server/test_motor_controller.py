"""Unit tests for motor_controller.py."""

import sys
import unittest
from unittest.mock import MagicMock, patch


# Mock spidev before importing motor_controller
if 'spidev' not in sys.modules:
    sys.modules['spidev'] = MagicMock()

import importlib
import motor_controller
importlib.reload(motor_controller)
from motor_controller import RoverController


class TestEncodeSpeed(unittest.TestCase):
    """Tests for the static encode_speed method."""

    def test_zero_encodes_to_128(self):
        assert RoverController.encode_speed(0) == 128

    def test_max_forward_encodes_to_255(self):
        assert RoverController.encode_speed(127) == 255

    def test_max_reverse_encodes_to_1(self):
        assert RoverController.encode_speed(-127) == 1

    def test_positive_value(self):
        assert RoverController.encode_speed(50) == 178

    def test_negative_value(self):
        assert RoverController.encode_speed(-50) == 78

    def test_clamps_above_127(self):
        assert RoverController.encode_speed(200) == 255

    def test_clamps_below_negative_127(self):
        assert RoverController.encode_speed(-200) == 1


class TestRoverControllerInit(unittest.TestCase):
    """Tests for RoverController initialization."""

    def test_successful_init(self):
        mock_spi_instance = MagicMock()
        mock_spidev_module = MagicMock()
        mock_spidev_module.SpiDev.return_value = mock_spi_instance

        with patch.dict(sys.modules, {'spidev': mock_spidev_module}):
            importlib.reload(motor_controller)
            from motor_controller import RoverController as RC
            controller = RC(bus=0, device=0, speed_hz=500000)

        assert controller.enabled is True
        mock_spi_instance.open.assert_called_with(0, 0)
        assert mock_spi_instance.max_speed_hz == 500000
        assert mock_spi_instance.mode == 0

    def test_init_spi_open_fails(self):
        mock_spi_instance = MagicMock()
        mock_spi_instance.open.side_effect = OSError("No SPI device")
        mock_spidev_module = MagicMock()
        mock_spidev_module.SpiDev.return_value = mock_spi_instance

        with patch.dict(sys.modules, {'spidev': mock_spidev_module}):
            importlib.reload(motor_controller)
            from motor_controller import RoverController as RC
            controller = RC()

        assert controller.enabled is False

    def test_init_without_spidev_module(self):
        with patch.object(motor_controller, '_SPI_AVAILABLE', False):
            controller = RoverController()
            assert controller.enabled is False


def _create_controller_with_mock():
    """Helper to create a RoverController with a fresh spidev mock.

    Returns:
        Tuple of (controller, mock_spi_instance)
    """
    mock_spi_instance = MagicMock()
    mock_spidev_module = MagicMock()
    mock_spidev_module.SpiDev.return_value = mock_spi_instance

    with patch.dict(sys.modules, {'spidev': mock_spidev_module}):
        importlib.reload(motor_controller)
        from motor_controller import RoverController as RC
        controller = RC()

    return controller, mock_spi_instance


class TestSendCommand(unittest.TestCase):
    """Tests for the send_command method."""

    def setUp(self):
        self.controller, self.mock_spi = _create_controller_with_mock()

    def test_send_forward_command(self):
        result = self.controller.send_command(127, 127)

        assert result is True
        self.mock_spi.xfer2.assert_called_with([0, 255, 255])

    def test_send_reverse_command(self):
        result = self.controller.send_command(-127, -127)

        assert result is True
        self.mock_spi.xfer2.assert_called_with([0, 1, 1])

    def test_send_stop_command(self):
        result = self.controller.send_command(0, 0)

        assert result is True
        self.mock_spi.xfer2.assert_called_with([0, 128, 128])

    def test_command_id_increments(self):
        self.controller.send_command(0, 0)
        self.controller.send_command(50, 50)

        calls = self.mock_spi.xfer2.call_args_list
        assert calls[0][0][0][0] == 0  # first command_id
        assert calls[1][0][0][0] == 1  # second command_id

    def test_command_id_wraps_at_255(self):
        self.controller._command_id = 255
        self.controller.send_command(0, 0)

        self.mock_spi.xfer2.assert_called_with([255, 128, 128])
        assert self.controller._command_id == 0

    def test_clamps_values_above_127(self):
        self.controller.send_command(200, 300)

        self.mock_spi.xfer2.assert_called_with([0, 255, 255])

    def test_clamps_values_below_negative_127(self):
        self.controller.send_command(-200, -300)

        self.mock_spi.xfer2.assert_called_with([0, 1, 1])

    def test_returns_false_when_disabled(self):
        self.controller.enabled = False
        result = self.controller.send_command(100, 100)

        assert result is False
        self.mock_spi.xfer2.assert_not_called()

    def test_retry_on_first_failure(self):
        self.mock_spi.xfer2.side_effect = [OSError("SPI error"), None]

        result = self.controller.send_command(50, 50)

        assert result is True
        assert self.mock_spi.xfer2.call_count == 2

    def test_discard_after_retry_failure(self):
        self.mock_spi.xfer2.side_effect = OSError("SPI error")

        result = self.controller.send_command(50, 50)

        assert result is False
        assert self.mock_spi.xfer2.call_count == 2

    def test_command_id_increments_on_failure(self):
        self.mock_spi.xfer2.side_effect = OSError("SPI error")

        self.controller.send_command(50, 50)

        assert self.controller._command_id == 1


class TestStop(unittest.TestCase):
    """Tests for the stop convenience method."""

    def setUp(self):
        self.controller, self.mock_spi = _create_controller_with_mock()

    def test_stop_sends_zero_zero(self):
        self.controller.stop()

        self.mock_spi.xfer2.assert_called_with([0, 128, 128])


class TestClose(unittest.TestCase):
    """Tests for the close method."""

    def setUp(self):
        self.controller, self.mock_spi = _create_controller_with_mock()

    def test_close_releases_spi(self):
        self.controller.close()

        self.mock_spi.close.assert_called_once()
        assert self.controller.enabled is False

    def test_close_handles_error(self):
        self.mock_spi.close.side_effect = OSError("close error")

        # Should not raise
        self.controller.close()
        assert self.controller.enabled is False


if __name__ == '__main__':
    unittest.main()

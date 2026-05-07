"""SPI motor controller for the SMARS Telepresence Rover.

Provides the RoverController class that communicates with the Arduino Pro Mini
motor controller via SPI. Handles offset encoding, command ID tracking, and
graceful fallback when SPI hardware is unavailable.
"""

import logging

logger = logging.getLogger(__name__)

try:
    import spidev
    _SPI_AVAILABLE = True
except ImportError:
    _SPI_AVAILABLE = False
    logger.warning("spidev module not available — motor control will be disabled")


class RoverController:
    """SPI-based motor controller interface.

    Sends 3-byte command packets [command_id, left_speed, right_speed] to the
    Arduino Pro Mini over SPI. Speed values use offset encoding where 128
    represents stop, values above 128 are forward, and below 128 are reverse.

    If SPI is unavailable at init time, the controller sets enabled=False and
    all commands become no-ops.
    """

    def __init__(self, bus: int = 0, device: int = 0, speed_hz: int = 500000):
        """Initialize SPI connection.

        Args:
            bus: SPI bus number (default 0).
            device: SPI device/chip-select number (default 0 = CE0).
            speed_hz: SPI clock speed in Hz (default 500000).
        """
        self.enabled = False
        self._command_id = 0
        self._spi = None

        if not _SPI_AVAILABLE:
            logger.error("SPI unavailable: spidev module not installed")
            return

        try:
            self._spi = spidev.SpiDev()
            self._spi.open(bus, device)
            self._spi.max_speed_hz = speed_hz
            self._spi.mode = 0
            self.enabled = True
            logger.info(
                "SPI motor controller initialized on bus %d, device %d at %d Hz",
                bus, device, speed_hz
            )
        except (OSError, IOError) as e:
            logger.error("Failed to open SPI device (bus=%d, device=%d): %s", bus, device, e)
            self._spi = None

    @staticmethod
    def encode_speed(value: int) -> int:
        """Convert signed speed (-127..127) to offset byte (1..255).

        Args:
            value: Signed speed value, will be clamped to -127..127.

        Returns:
            Offset-encoded byte in range 1..255.
        """
        clamped = max(-127, min(127, value))
        return clamped + 128

    def send_command(self, left: int, right: int) -> bool:
        """Send motor command over SPI.

        Clamps left/right to -127..127, encodes using offset encoding,
        and transmits a 3-byte packet. Retries once on SPI error.

        Args:
            left: Left motor speed (-127 to 127).
            right: Right motor speed (-127 to 127).

        Returns:
            True if command was sent successfully, False otherwise.
        """
        if not self.enabled:
            return False

        left_byte = self.encode_speed(left)
        right_byte = self.encode_speed(right)
        packet = [self._command_id, left_byte, right_byte]

        # Debug: print actual bytes being sent over SPI
        print(f"SPI TX: id={self._command_id} L_byte={left_byte} R_byte={right_byte} (L={left} R={right})")

        success = self._transmit(packet)

        if not success:
            # Single retry before discard
            logger.warning("SPI write failed, retrying command_id=%d", self._command_id)
            success = self._transmit(packet)
            if not success:
                logger.error("SPI write failed after retry, discarding command_id=%d", self._command_id)

        # Always increment command_id regardless of success
        self._command_id = (self._command_id + 1) % 256

        return success

    def _transmit(self, packet: list) -> bool:
        """Transmit a raw packet over SPI.

        Args:
            packet: List of byte values to send.

        Returns:
            True on success, False on error.
        """
        try:
            self._spi.xfer2(packet)
            return True
        except (OSError, IOError) as e:
            logger.error("SPI transmission error: %s", e)
            return False

    def stop(self) -> bool:
        """Send stop command (left=0, right=0).

        Returns:
            True if command was sent successfully, False otherwise.
        """
        return self.send_command(0, 0)

    def close(self):
        """Release SPI resources."""
        if self._spi is not None:
            try:
                self._spi.close()
            except (OSError, IOError) as e:
                logger.error("Error closing SPI: %s", e)
            self._spi = None
        self.enabled = False
        logger.info("SPI motor controller closed")

"""UDP motor control server for the SMARS Telepresence Rover.

Receives 4-byte UDP packets from the client and forwards motor commands
to the Arduino Pro Mini via SPI. Runs as its own process for maximum
responsiveness — no GIL, no event loop, no buffering.

UDP packet format (4 bytes):
    [0] = 0xAA (sync byte)
    [1] = left speed (0-255, offset encoded: 128 = stop)
    [2] = right speed (0-255, offset encoded: 128 = stop)
    [3] = sequence number (0-255, for debugging)

SPI packet to Arduino (4 bytes):
    [0] = 0xAA (sync byte)
    [1] = command_id (0-255, incrementing)
    [2] = left speed (0-255, offset encoded)
    [3] = right speed (0-255, offset encoded)
"""

import logging
import socket
import time

logger = logging.getLogger(__name__)

UDP_PORT = 8082
TIMEOUT_MS = 500  # Stop motors if no command received for 500ms


def run_motor_server(spi_bus=0, spi_device=0, spi_speed=500000):
    """Run the UDP motor control server.

    Listens for UDP packets and forwards commands to Arduino via SPI.
    Stops motors automatically if no commands received within timeout.
    """
    try:
        import spidev
    except ImportError:
        logger.error("spidev not available — motor control disabled")
        return

    # Initialize SPI
    spi = spidev.SpiDev()
    try:
        spi.open(spi_bus, spi_device)
        spi.max_speed_hz = spi_speed
        spi.mode = 0
        logger.info("Motor UDP: SPI initialized (bus=%d, dev=%d, %dHz)", spi_bus, spi_device, spi_speed)
    except (OSError, IOError) as e:
        logger.error("Motor UDP: Failed to open SPI: %s", e)
        return

    # Initialize UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', UDP_PORT))
    sock.settimeout(0.1)  # 100ms timeout for checking stop condition
    logger.info("Motor UDP: listening on port %d", UDP_PORT)

    command_id = 0
    last_command_time = time.time()
    motors_active = False

    try:
        while True:
            try:
                data, addr = sock.recvfrom(16)
            except socket.timeout:
                # Check if we need to stop motors (no commands for TIMEOUT_MS)
                if motors_active and (time.time() - last_command_time) > (TIMEOUT_MS / 1000.0):
                    # Send stop command
                    spi.xfer2([0xAA, command_id, 128, 128])
                    command_id = (command_id + 1) % 256
                    motors_active = False
                continue

            # Validate packet: must be 4 bytes starting with 0xAA
            if len(data) < 4 or data[0] != 0xAA:
                continue

            left_byte = data[1]
            right_byte = data[2]
            # data[3] is client sequence number (ignored, just for debugging)

            # Forward to Arduino via SPI — original 3-byte protocol
            # [command_id, left_speed, right_speed]
            spi.xfer2([command_id, left_byte, right_byte])
            command_id = (command_id + 1) % 256

            last_command_time = time.time()
            motors_active = (left_byte != 128 or right_byte != 128)

    except KeyboardInterrupt:
        pass
    finally:
        # Stop motors on shutdown
        spi.xfer2([0xAA, command_id, 128, 128])
        spi.close()
        sock.close()
        logger.info("Motor UDP: shutdown complete")

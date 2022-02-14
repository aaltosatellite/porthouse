"""
    Interface class for controlling Aalto Satellites Rotator controller.
"""

import asyncio
import time
import serial # serial_asyncio

from typing import Tuple, Optional


class RotatorError(Exception):
    """ Exception class for all rotator hardware """

class ControllerBoxError(RotatorError):
    """ Exception class for all rotator hardware error returned by control box """

PositionType = Tuple[float, float]

class ControllerBox:
    """
    Rotator controller wrapper class.
    """

    current_position: PositionType
    az_min: int
    az_max: int
    el_min: int
    el_max: int

    debug: bool

    def __init__(self,
            address: str,
            baudrate: int=115200,
            az_min: int =-90,
            az_max: int =450,
            el_min: int =0,
            el_max: int =90,
            debug=False):
        """
        Initialzie controller box including serial com to controller box.

        Args:
            address: Controller serial port address
            baudrate: Controller serial baudrate
            az_min: Minimum allowed azimuth
            az_max: Maximum allowed azimuth
            el_min: Minimum allowed elecation
            el_max: Maximum allowed elecation
            debug: Debug flag. If true, debug information is printedout to log file during runtime.
        """

        self.az_min = az_min
        self.az_max = az_max
        self.el_min = el_min
        self.el_max = el_max
        self.debug = debug
        self.current_position = (0.0, 0.0)
        self.err_cnt = 0

        if self.debug:
            self.log = open(f"controlbox_debug_{time.time():d}.log", "w")

        # Creates and opens serial com
        self.ser = serial.Serial(port=address, baudrate=baudrate, timeout=0.3)


    def open(self):
        """Open serial com to controller box."""
        self.flush_buffers()
        self.ser.open()

    def close(self):
        """Close serial com to controller box."""
        self.ser.close()
        self.flush_buffers()

    def reset(self, wait_time=1):
        """Reset serial com to controller box."""
        self.close()
        time.sleep(wait_time)
        self.open()

    def flush_buffers(self):
        """ Clear/flush the input and output buffer of serial com. """
        self.ser.flushInput()
        self.ser.flushOutput()


    def _read_response(self) -> bytes:
        """
        Read one line input of serial com.

        Returns:
            Received `bytes` from the controller box

        Raises:
            `ControllerBoxError` - in case the controller box encoutered an error.
        """

        try:
            rsp = self.ser.readline()

            if self.debug:
                self.log.write(f"{time.time()} READ: {rsp}\n")
                self.log.flush()

        except Exception as e:
            raise ControllerBoxError(
                f"Error while reading message from controller box: {e}"
            ) from e

        try:
            # Convert to ascii
            rsp = rsp.decode("ascii").strip()
        except Exception as e: # Just crap on the UART line
            return b""

        # Raise error if the line starts with "Error"
        if rsp.startswith("Error: "):
            raise ControllerBoxError(rsp[7:])

        return rsp


    def _write_command(self, cmd: bytes) -> None:
        """
        Write message to controller box via serial port.

        Args:
            cmd:

        Raises:
            `ControllerBoxError` - in case the controller box encoutered an error.
        """

        if isinstance(cmd, str):
            cmd += '\n' # Add newline
            cmd = cmd.decode("ascii")

        elif not isinstance(cmd, bytes):
            raise ValueError("Wrong input format")

        try:
            ret = self.ser.write(cmd)

            if self.debug:
                self.log.write(f"{time.time()} WRITE: {cmd}\n")
                self.log.flush()

        except serial.SerialTimeoutException as e:
            raise ControllerBoxError("Serial connection to controller box timed out: ", e)

        except Exception as e:
            raise ControllerBoxError("Communication error while writing to controller box: ", e) from e



    def stop(self) -> None:
        """
        Stop rotator movement
        """
        self._write_command("S")
        self._read_response()


    def get_position(self) -> PositionType:
        """
        Read rotator's current position.

        Returns:
            A tuple containing current azimuth and elevation.
        """

        self._write_command("P -s")
        self.current_position = ControllerBox._parse_position_output(self._read_response())

        self.err_cnt = 0 # Reset error counter

        return self.current_position


    def set_position(self,
            az: float,
            el: float,
            rounding: int=1,
            shortest_path: bool=True
        ) -> PositionType:
        """
        Set azimuth and elevation to precision of rounding and threshold.
        Additionally, possible to not use shortest path.

        Args:
            az: Target azimuth angle
            el: Target elevation angle
            rounding: Number of decimals
            shortets_path: Should the rotator try move using shortest path

        Returns:
            Returns the current rotator position as tuple

        Raises:
            `ControllerBoxError` - in case the controller box encoutered an error.
        """

        # Check whether az and el are within allowed limits
        if az < self.az_min or az > self.az_max:
            raise ControllerBoxError("Azimuth value outside allowed limits.")
        if el < self.el_min or el > self.el_max:
            raise ControllerBoxError("Elevation value outside allowed limits.")

        if shortest_path:
            self._write_command(f"MS -a {round(az, rounding)}")
            self._write_command(f"MS -e {round(el, rounding)}")
        else:
            self._write_command(f"M -a {round(az, rounding)}")
            self._write_command(f"M -e {round(el, rounding)}")

        self._read_response()

        return self.get_position_target()


    def get_position_target(self) -> PositionType:
        """
        Get position where the rotator is moving to.

        Returns:
            Target position as tuple

        Raises:
            `ControllerBoxError` - in case the controller box encoutered an error.
        """

        self._write_command("M -s")
        return ControllerBox._parse_position_output(self._read_response())


    def get_position_range(self) -> Tuple[float, float, float, float]:
        """
        Read back the allowed range of azimuth (az) and elevation (el) coordinates.

        Returns:
            A tuple containing ranges: az_min, az_max, el_min, el_max

        Raises:
            `ControllerBoxError` - in case the controller box encoutered an error.
        """

        self._write_command("R+ -s")
        self.az_max, self.el_max = ControllerBox._parse_position_output(self._read_response())

        self._write_command("R- -s")
        self.az_min, self.el_min = ControllerBox._parse_position_output(self._read_response())

        return (self.az_min, self.az_max, self.el_min, self.el_max)


    def set_position_range(self,
           az_min: Optional[float]=None,
           az_max: Optional[float]=None,
           el_min: Optional[float]=None,
           el_max: Optional[float]=None,
           rounding: int=1):
        """
        Sets azimuth and elevation range limts.

        Raises:
            `ControllerBoxError` - in case the controller box encoutered an error.
        """
        if az_min is not None:
            self._write_command(f"R- -a {round(az_min, rounding)}")
            self._read_response() # Just "OK" ack

        if az_max is not None:
            self._write_command(f"R+ -a {round(az_max, rounding)}")
            self._read_response() # Just "OK" ack

        if el_min is not None:
            self._write_command(f"R- -e {round(el_min, rounding)}")
            self._read_response() # Just "OK" ack

        if el_max is not None:
            self._write_command(f"R+ -e {round(el_max, rounding)}")
            self._read_response() # Just "OK" ack

        return self.get_position_range()


    def calibrate(self,
            az: float,
            el: float,
            rounding: int=1,
            timeout=120
        ) -> PositionType:
        """
        Calibrate azimuth and elevation by moving to position values
        and redefining as new (0, 0) position.

        Remarks:
            This command will **block** the execution till the calibration movement
            has been completed

        Args:
            az:
            el:
            rounding:
            timeout:

        Raises:
            `ControllerBoxError` - in case the controller box encoutered an error.
        """

        self.set_position(az, el, rounding=rounding, shortest_path=False)

        timeout = time.time() + timeout
        while (not self._check_pointing((az, el)) and timeout < time.time()):
            time.sleep(1)
            self.get_position()

        # Check if the target was achieved
        if self._check_pointing((az, el)):

            # Force current position to be 0,0
            self._write_command("P -a 0")
            self._read_response()

            self._write_command("P -e 0")
            self._read_response()
        else:
            raise ControllerBoxError(
                "The setpoint was not reached during calibration!")

        return self.get_position()


    def _get_duty_cycle(self) -> Tuple[int, int, int, int]:
        """
        Get dutycycle range for azimuth and elevation.

        Returns:
            A tuple with (az_min, az_max, el_min, el_max) dutycycles.

        Raises:
            `ControllerBoxError` - in case the controller box encoutered an error.
        """

        self._write_command("D+ -s")
        range_max = ControllerBox._parse_position_output(self._read_response())

        self._write_command("D- -s")
        range_min = ControllerBox._parse_position_output(self._read_response())

        return (range_min[0], range_max[0], range_min[1], range_max[1])


    def _set_duty_cycle(self,
            az_duty_min: Optional[int]=None,
            az_duty_max: Optional[int]=None,
            el_duty_min: Optional[int]=None,
            el_duty_max: Optional[int]=None
        ) -> None:
        """
            Set dutycycle range for azimuth and elevation.

        Args:
            az_duty_min: Minimum duty cycle (start speed) for azimuth
            az_duty_max: Maximum duty cycle (max speed) for azimuth
            el_duty_min: Minimum duty cycle (start speed) for elevation
            el_duty_max: Maximum duty cycle (max speed) for elevation

        Raises:
            `ControllerBoxError` - in case the controller box encoutered an error.
        """

        if az_duty_min is not None:
            self._write_command(f"D- -a {az_duty_min:d}")
            self._read_response()

        if az_duty_max is not None:
            self._write_command(f"D+ -a {az_duty_max:d}")
            self._read_response()

        if el_duty_min is not None:
            self._write_command(f"D- -e {el_duty_min:d}")
            self._read_response()

        if el_duty_max is not None:
            self._write_command(f"D+ -e {el_duty_max:d}")
            self._read_response()


    def _check_pointing(self, target_position: PositionType, accuracy: float=0.1) -> bool:
        """
        Checks if antenna is pointing to target.
        Takes finite accuracy of rotators into account by allowing some dead-zone.

        Args:
            target_position:
            accuracy:

        Returns:
            True if antenna is pointing to target within limits.
        """

        return  abs(self.current_position[0] - target_position[0]) <= accuracy \
            and abs(self.current_position[1] - target_position[1]) <= accuracy


    @staticmethod
    def _parse_position_output(output: bytes) -> PositionType:
        """
        Parse azimuth and elevation output of rotator control box.

        Expected input format: "Az: xxx.x <units> El: xxx.x <units>"
        """

        if not isinstance(output, str):
            raise ValueError("Bytes expected")

        try:
            parsed_output = output.split()
            return float(parsed_output[1]), float(parsed_output[4])

        except ValueError:
            raise ControllerBoxError(f"Failed to parse output format: {output}")

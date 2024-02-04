"""
    Interface class for controlling Aalto Satellites Rotator controller.
"""

import os
import time
import serial  # serial_asyncio

from typing import Tuple, Optional, List, Union

from .base import RotatorController, RotatorError, PositionType


class ControllerBoxError(RotatorError):
    """ Exception class for all rotator hardware error returned by the Aalto controller box """


class ControllerBox(RotatorController):
    """
    Controller class for Aalto rotator controller box
    """

    def __init__(self,
                 address: str,
                 baudrate: int = 115200,
                 az_min: float = -90,
                 az_max: float = 450,
                 el_min: float = 0,
                 el_max: float = 90,
                 horizon_map_file: Optional[str] = None,
                 min_sun_angle: Optional[float] = None,
                 debug: bool = False,
                 prefix="") -> None:
        """
        Initialize controller box including serial com to controller box.

        Args:
            address: Controller serial port address
            baudrate: Controller serial baudrate
            az_min: Minimum allowed azimuth angle
            az_max: Maximum allowed azimuth angle
            el_min: Minimum allowed elevation angle
            el_max: Maximum allowed elevation angle
            horizon_map_file: A file that can be read with numpy load and restults in two column array (az, el), where
                              rows are points on the horizon. If set, the horizon map is used to limit the elevation.
            min_sun_angle: Minimum allowed sun angle
            debug: Debug flag. If true, debug information is logged to a file during runtime.
        """

        super().__init__(address, az_min, az_max, el_min, el_max, horizon_map_file, min_sun_angle, debug)

        self.err_cnt = 0

        if self.debug:
            os.makedirs("logs", exist_ok=True)
            self.log = open(f"logs/{prefix}_debug_{time.time():.0f}.log", "w")

        # Creates and opens serial com
        self.ser = serial.Serial(port=address, baudrate=baudrate, timeout=0.5)
        self.set_position_range(az_min, az_max, el_min, el_max)
        self.get_position()         # get current_position, also move to valid position if currently invalid

    def open(self):
        self.flush_buffers()
        self.ser.open()

    def close(self):
        self.ser.close()
        self.flush_buffers()

    def reset(self, wait_time=1):
        self.close()
        time.sleep(wait_time)
        self.open()

    def flush_buffers(self):
        self.ser.flushInput()
        self.ser.flushOutput()

    def stop(self) -> None:
        self._write_command(b"S")
        self._read_response()

    def get_position(self, with_timestamp=False) -> Union[PositionType, Tuple[PositionType, float]]:
        self._write_command(b"P -s")
        self.current_pos_ts = time.time()
        self.current_position = self._parse_position_output(self._read_response())
        self.err_cnt = 0  # Reset error counter

        self.maybe_enforce_limits()
        return self.current_position if not with_timestamp else (self.current_position, self.current_pos_ts)

    def set_position(self,
                     az: float,
                     el: float,
                     ts: Optional[float] = None,
                     rounding: int = 1,
                     shortest_path: bool = True) -> PositionType:

        # Check whether az and el are within allowed limits
        self.position_valid(az, el, raise_error=True)
        self.target_position = (az, el)
        self.target_pos_ts = ts or time.time()

        if shortest_path:
            self._write_command(f"MS -a {round(az, rounding)}".encode("ascii"))
            self._write_command(f"MS -e {round(el, rounding)}".encode("ascii"))
        else:
            self._write_command(f"M -a {round(az, rounding)}".encode("ascii"))
            self._write_command(f"M -e {round(el, rounding)}".encode("ascii"))

        self._read_response()

        return self.get_position_target()

    def get_position_target(self) -> PositionType:
        self._write_command(b"M -s")
        self.target_position = ControllerBox._parse_position_output(self._read_response())
        return self.target_position

    def get_position_range(self) -> Tuple[float, float, float, float]:
        self._write_command(b"R+ -s")
        self.az_max, self.el_max = ControllerBox._parse_position_output(self._read_response())

        self._write_command(b"R- -s")
        self.az_min, self.el_min = ControllerBox._parse_position_output(self._read_response())

        return self.az_min, self.az_max, self.el_min, self.el_max

    def set_position_range(self,
                           az_min: Optional[float] = None,
                           az_max: Optional[float] = None,
                           el_min: Optional[float] = None,
                           el_max: Optional[float] = None,
                           rounding: int = 1):

        super().set_position_range(az_min, az_max, el_min, el_max, rounding)

        if az_min is not None:
            self._write_command(f"R- -a {round(az_min, rounding)}".encode("ascii"))
            self._read_response()  # Just "OK" ack

        if az_max is not None:
            self._write_command(f"R+ -a {round(az_max, rounding)}".encode("ascii"))
            self._read_response()  # Just "OK" ack

        if el_min is not None:
            self._write_command(f"R- -e {round(el_min, rounding)}".encode("ascii"))
            self._read_response()  # Just "OK" ack

        if el_max is not None:
            self._write_command(f"R+ -e {round(el_max, rounding)}".encode("ascii"))
            self._read_response()  # Just "OK" ack

        return self.get_position_range()

    def reset_position(self,
                       az: float,
                       el: float) -> None:

        # Force current position to be az, el
        self._write_command(f"P -a {az: .1f}".encode("ascii"))
        self._read_response()

        self._write_command(f"P -e {el: .1f}".encode("ascii"))
        self._read_response()

        # set target position to current position
        self.target_position = (az, el)

        # update current_position, also move to valid position if currently invalid
        self.get_position()

    def get_dutycycle_range(self) -> Tuple[int, int, int, int]:
        self._write_command(b"D+ -s")
        range_max = ControllerBox._parse_position_output(self._read_response())

        self._write_command(b"D- -s")
        range_min = ControllerBox._parse_position_output(self._read_response())

        return int(range_min[0]), int(range_max[0]), int(range_min[1]), int(range_max[1])

    def set_dutycycle_range(self,
                            az_duty_min: Optional[int]=None,
                            az_duty_max: Optional[int]=None,
                            el_duty_min: Optional[int]=None,
                            el_duty_max: Optional[int]=None) -> None:

        if az_duty_min is not None:
            self._write_command(f"D- -a {az_duty_min:d}".encode("ascii"))
            self._read_response()

        if az_duty_max is not None:
            self._write_command(f"D+ -a {az_duty_max:d}".encode("ascii"))
            self._read_response()

        if el_duty_min is not None:
            self._write_command(f"D- -e {el_duty_min:d}".encode("ascii"))
            self._read_response()

        if el_duty_max is not None:
            self._write_command(f"D+ -e {el_duty_max:d}".encode("ascii"))
            self._read_response()

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

        # Raise error if the line starts with "Error"
        if rsp.startswith(b"Error: "):
            raise ControllerBoxError(str(rsp[7:]))

        return rsp

    def _write_command(self, cmd: bytes) -> None:
        """
        Write message to controller box via serial port.

        Args:
            cmd:

        Raises:
            `ControllerBoxError` - in case the controller box encoutered an error.
        """

        if not isinstance(cmd, bytes):
            raise ValueError("Wrong input format")

        if cmd[-1] != b"\r":
            cmd += b"\r"

        try:
            ret = self.ser.write(cmd)

            if self.debug:
                self.log.write(f"{time.time()} WRITE (bytes {ret}): {cmd}\n")
                self.log.flush()

        except serial.SerialTimeoutException as e:
            raise ControllerBoxError("Serial connection to controller box timed out: ", e)

        except Exception as e:
            raise ControllerBoxError("Communication error while writing to controller box: ", e) from e

    @staticmethod
    def _parse_position_output(output: bytes) -> PositionType:
        """
        Parse azimuth and elevation output of rotator control box.

        Expected input format: "Az: xxx.x <units> El: xxx.x <units>"
        """

        if not isinstance(output, bytes):
            raise ValueError("Bytes expected")

        try:
            str_output = output.decode("ascii").strip()
            parsed_output = str_output.split()
            return float(parsed_output[1]), float(parsed_output[4])

        except Exception as e:
            raise ControllerBoxError(f"Failed to parse output format: {output}") from e

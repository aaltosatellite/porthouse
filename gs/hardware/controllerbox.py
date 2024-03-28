"""
    Interface class for controlling Aalto Satellites Rotator controller.
"""

import os
import time
import math
import struct
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
                 rotator_model: Optional[dict] = None,
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
            rotator_model: A dictionary containing the rotator model that is used to transform real azimuth and
                           elevation values to motor angles.
            horizon_map_file: A file that can be read with numpy load and results in two column array (az, el), where
                              rows are points on the horizon. If set, the horizon map is used to limit the elevation.
            min_sun_angle: Minimum allowed sun angle
            debug: Debug flag. If true, debug information is logged to a file during runtime.
        """

        super().__init__(address, az_min, az_max, el_min, el_max, rotator_model, horizon_map_file,
                         min_sun_angle, debug)

        self.err_cnt = 0
        self.prefix = prefix
        self.log = None
        self.mlog = None

        if self.debug:  # TODO: where would be best to put this?
            os.makedirs("logs", exist_ok=True)
            self.log = open(f"logs/{self.prefix}_debug_{time.time():.0f}.log", "w")

        # Creates and opens serial com
        self.ser = serial.Serial(port=address, baudrate=baudrate, timeout=0.5)
        self.set_position_range(az_min, az_max, el_min, el_max)
        self.get_position()         # get current_position, also move to valid position if currently invalid

    def _open_mlog(self):
        os.makedirs("logs", exist_ok=True)
        self.mlog = open(f"logs/{self.prefix}_motion_{time.time():.0f}.bin", "wb")

    def open(self):
        self.flush_buffers()
        self.ser.open()

    def close(self):
        self.ser.close()
        self.flush_buffers()
        if self.debug:
            self.log.close()
        if self.mlog:
            self.mlog.close()

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
        motor_pos = self._parse_position_output(self._read_response())
        self.current_position = self.rotator_model.to_real(*motor_pos)
        self.err_cnt = 0  # Reset error counter

        self.maybe_enforce_limits()
        return self.current_position if not with_timestamp else (self.current_position, self.current_pos_ts)

    def set_position(self,
                     az: float,
                     el: float,
                     vel: Optional[Tuple[float, float]] = None,
                     ts: Optional[float] = None,
                     shortest_path: bool = True) -> PositionType:

        # Check whether az and el are within allowed limits
        self.position_valid(az, el, raise_error=True)
        self.target_position = (az, el)
        self.target_velocity = vel or (0.0, 0.0)
        self.target_pos_ts = ts or time.time()
        maz, mel = self.rotator_model.to_motor(az, el)

        if shortest_path:
            self._write_command(f"MS -a {maz:.2f}".encode("ascii"))
            self._write_command(f"MS -e {mel:.2f}".encode("ascii"))
        else:
            self._write_command(f"M -a {maz:.2f}".encode("ascii"))
            self._write_command(f"M -e {mel:.2f}".encode("ascii"))

        self._read_response()

        # set target velocities
        mazv, melv = self.target_velocity  # TODO: convert velocities to motor velocities
        try:
            # TODO: deploy new code to all controllers (UHF & S-band also)
            self._write_command(f"MV -a {mazv:.4f}".encode("ascii"))
            self._write_command(f"MV -e {melv:.4f}".encode("ascii"))
            self._read_response()
        except ControllerBoxError as e:
            pass

        return self.get_position_target()

    def get_position_target(self, get_vel=False) -> PositionType | Tuple[PositionType, PositionType]:
        self._write_command(b"M -s")
        trg_motor_pos = self._parse_position_output(self._read_response())
        self.target_position = self.rotator_model.to_real(*trg_motor_pos)

        if get_vel:
            self._write_command(b"MV -s")   # NOTE: not yet deployed for original UHF controller
            trg_motor_vel = self._parse_position_output(self._read_response())
            self.target_velocity = trg_motor_vel  # TODO: self.rotator_model.to_real_vel(*trg_motor_vel)

        return self.target_position if not get_vel else (self.target_position, self.target_velocity)

    def get_position_range(self) -> Tuple[float, float, float, float]:
        """
        Get the allowed position range in motor angles from the controller
        """
        self._write_command(b"R+ -s")
        self.az_max, self.el_max = ControllerBox._parse_position_output(self._read_response())

        self._write_command(b"R- -s")
        self.az_min, self.el_min = ControllerBox._parse_position_output(self._read_response())

        return self.az_min, self.az_max, self.el_min, self.el_max

    def set_position_range(self,
                           az_min: Optional[float] = None,
                           az_max: Optional[float] = None,
                           el_min: Optional[float] = None,
                           el_max: Optional[float] = None) -> Tuple[float, float, float, float]:
        """
        Set the allowed position range in motor angles from the controller
        """
        super().set_position_range(az_min, az_max, el_min, el_max)

        if az_min is not None:
            self._write_command(f"R- -a {az_min:.2f}".encode("ascii"))
            self._read_response()  # Just "OK" ack

        if az_max is not None:
            self._write_command(f"R+ -a {az_max:.2f}".encode("ascii"))
            self._read_response()  # Just "OK" ack

        if el_min is not None:
            self._write_command(f"R- -e {el_min:.2f}".encode("ascii"))
            self._read_response()  # Just "OK" ack

        if el_max is not None:
            self._write_command(f"R+ -e {el_max:.2f}".encode("ascii"))
            self._read_response()  # Just "OK" ack

        return self.get_position_range()

    def reset_position(self,
                       az: float,
                       el: float) -> None:

        maz, mel = self.rotator_model.to_motor(az, el)

        # Force current position to be az, el
        self._write_command(f"P -a {maz: .2f}".encode("ascii"))
        self._write_command(f"P -e {mel: .2f}".encode("ascii"))
        self._read_response()

        self.target_position = (az, el)

        # update current_position, also move to valid position if currently invalid
        self.get_position()


    def get_dutycycle_range(self) -> Tuple[float, float, float, float]:
        self._write_command(b"D+ -s")
        range_max = ControllerBox._parse_position_output(self._read_response())

        self._write_command(b"D- -s")
        range_min = ControllerBox._parse_position_output(self._read_response())

        return float(range_min[0]), float(range_max[0]), float(range_min[1]), float(range_max[1])

    def set_dutycycle_range(self,
                            az_duty_min: Optional[float]=None,
                            az_duty_max: Optional[float]=None,
                            el_duty_min: Optional[float]=None,
                            el_duty_max: Optional[float]=None) -> None:

        if az_duty_min is not None:
            self._write_command(f"D- -a {az_duty_min:.2f}".encode("ascii"))
            self._read_response()

        if az_duty_max is not None:
            self._write_command(f"D+ -a {az_duty_max:.2f}".encode("ascii"))
            self._read_response()

        if el_duty_min is not None:
            self._write_command(f"D- -e {el_duty_min:.2f}".encode("ascii"))
            self._read_response()

        if el_duty_max is not None:
            self._write_command(f"D+ -e {el_duty_max:.2f}".encode("ascii"))
            self._read_response()

    def pop_motion_log(self):
        """
        Reads, resets and returns the motion log from the controller box. Call this function
        frequently enough to avoid log overflow.
        """
        if not self.mlog:
            self._open_mlog()

        ts = struct.pack('<Q', time.time_ns())
        self._write_command(b"L")
        sep = struct.pack('<Iffff', 0, math.nan, math.nan, math.nan, math.nan)
        bytes = self._read_bin_resp(sep)
        if not bytes.endswith(sep):
            raise ControllerBoxError(f"Failed to read motion log, total bytes read: "
                                     f"{len(bytes)}, last 20 bytes: 0x{bytes[-20:].hex()}, "
                                     f"should have been 0x{sep.hex()}")
        self.mlog.write(ts)
        self.mlog.write(bytes)
        self.mlog.flush()

    def _read_bin_resp(self, end_seq: bytes) -> bytes:
        """
        Read until (and including) `end_seq` from the serial port.

        Returns:
            Received `bytes` from the controller box
        """
        rsp = b''
        while not rsp.endswith(end_seq):
            tmp = self.ser.read_until(end_seq)
            rsp += tmp
            if len(tmp) == 0:
                break
        return rsp

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

        Expected input format: "Az: xxx.xx <units> El: xxx.xx <units>"
        """

        if not isinstance(output, bytes):
            raise ValueError("Bytes expected")

        try:
            str_output = output.decode("ascii").strip()
            parsed_output = str_output.split()
            return float(parsed_output[1]), float(parsed_output[4])

        except Exception as e:
            raise ControllerBoxError(f"Failed to parse output format: {output}") from e

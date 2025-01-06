"""
    Interface class for controlling Aalto Satellites Rotator controller.
"""

import os
import time
import math
import struct
import asyncio
import serial
from serial_asyncio import open_serial_connection

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
                 control_sw_version=1,
                 log=None,
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
                         min_sun_angle, control_sw_version, debug, log)

        self.err_cnt = 0
        self.prefix = prefix
        self.sync_offset = 0.003     # initial guess for time-sync offset
        self.epoch = time.time_ns()
        self.dlog = None
        self.mlog = None

        if self.debug:  # TODO: where would be best to put this?
            os.makedirs("logs", exist_ok=True)
            self.dlog = open(f"logs/{self.prefix}_debug_{time.time():.0f}.log", "w")

        # serial connection opened in during call to setup()
        self._address = address
        self._baudrate = baudrate
        self._limits = (az_min, az_max, el_min, el_max)
        self._reader = None
        self._writer = None
        self._lock = asyncio.Lock()

    def _open_mlog(self):
        os.makedirs("logs", exist_ok=True)
        self.mlog = open(f"logs/{self.prefix}_motion_{time.time():.0f}.bin", "wb")

    async def setup(self):
        async with self._lock:
            self._reader, self._writer = await open_serial_connection(url=self._address,
                                                                      baudrate=self._baudrate,
                                                                      timeout=0.5)
        await self.set_position_range(*self._limits)
        await self.get_position()         # get current_position, also move to valid position if currently invalid

    async def stop(self) -> None:
        await self._rpc(b"S")

    async def get_position(self, with_timestamp=False) -> Union[PositionType, Tuple[PositionType, float]]:
        res = await self._rpc(b"P -s")
        self.current_pos_ts = time.time()
        motor_pos = self._parse_position_output(res)
        self.current_position = self.rotator_model.to_real(*motor_pos)
        self.err_cnt = 0  # Reset error counter

        await self.maybe_enforce_limits()
        return self.current_position if not with_timestamp else (self.current_position, self.current_pos_ts)

    async def set_position(self,
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

        if self.control_sw_version > 2:
            adj = 1.25e9 if True else 0.0  # anticipate satellite movement by 1.25 s?
            t0 = (time.time_ns() + adj - self.epoch) / 1e9
            resp = await self._rpc(f"ST {t0 + self.sync_offset:.6f}".encode("ascii"))
            t1 = (time.time_ns() + adj - self.epoch) / 1e9
            self.sync_offset = (t1 - t0) / 2
            dt, gain = self._parse_position_output(resp)
            self.log.debug(f"Time-sync, rtt: {t1-t0:.6f} s, diff: {dt:.6f} s, gain: {gain:.3e} s/tick")

        if self.control_sw_version > 2 and shortest_path:
            ts = self.target_pos_ts - self.epoch/1e9
            await self._rpc(f"WA {ts:.3f} {maz:.2f} {mel:.2f}".encode("ascii"))
        else:
            if shortest_path:
                await self._rpc(f"MS -a {maz:.2f}".encode("ascii"))
                await self._rpc(f"MS -e {mel:.2f}".encode("ascii"))
            else:
                await self._rpc(f"M -a {maz:.2f}".encode("ascii"))
                await self._rpc(f"M -e {mel:.2f}".encode("ascii"))

        return await self.get_position_target()

    async def get_position_target(self, get_vel=False) -> PositionType | Tuple[PositionType, PositionType]:
        res = await self._rpc(b"M -s")
        trg_motor_pos = self._parse_position_output(res)

        if get_vel and self.control_sw_version > 1:
            res = await self._rpc(b"MV -s")   # NOTE: not yet deployed for original UHF controller
            trg_motor_vel = self._parse_position_output(res)
            self.target_position, self.target_velocity = self.rotator_model.to_real(*trg_motor_pos, *trg_motor_vel)
        else:
            self.target_position = self.rotator_model.to_real(*trg_motor_pos)

        return self.target_position if not get_vel else (self.target_position, self.target_velocity)

    async def get_position_range(self) -> Tuple[float, float, float, float]:
        """
        Get the allowed position range in motor angles from the controller
        """
        res = await self._rpc(b"R+ -s")
        self.az_max, self.el_max = ControllerBox._parse_position_output(res)

        res = await self._rpc(b"R- -s")
        self.az_min, self.el_min = ControllerBox._parse_position_output(res)

        return self.az_min, self.az_max, self.el_min, self.el_max

    async def set_position_range(self,
                           az_min: Optional[float] = None,
                           az_max: Optional[float] = None,
                           el_min: Optional[float] = None,
                           el_max: Optional[float] = None) -> Tuple[float, float, float, float]:
        """
        Set the allowed position range in motor angles from the controller
        """
        await super().set_position_range(az_min, az_max, el_min, el_max)

        if az_min is not None:
            await self._rpc(f"R- -a {az_min:.2f}".encode("ascii"))

        if az_max is not None:
            await self._rpc(f"R+ -a {az_max:.2f}".encode("ascii"))

        if el_min is not None:
            await self._rpc(f"R- -e {el_min:.2f}".encode("ascii"))

        if el_max is not None:
            await self._rpc(f"R+ -e {el_max:.2f}".encode("ascii"))

        return await self.get_position_range()

    async def reset_position(self,
                       az: float,
                       el: float) -> None:

        self.rotator_model.az_off = 0
        self.rotator_model.el_off = 0
        maz, mel = self.rotator_model.to_motor(az, el)

        # Force current position to be az, el
        await self._rpc(f"P -a {maz: .2f}".encode("ascii"))
        await self._rpc(f"P -e {mel: .2f}".encode("ascii"))

        self.target_position = (az, el)

        # update current_position, also move to valid position if currently invalid
        await self.get_position()

    async def get_dutycycle_range(self) -> Tuple[float, float, float, float]:
        res = await self._rpc(b"D+ -s")
        range_max = ControllerBox._parse_position_output(res)

        res = await self._rpc(b"D- -s")
        range_min = ControllerBox._parse_position_output(res)

        return float(range_min[0]), float(range_max[0]), float(range_min[1]), float(range_max[1])

    async def set_dutycycle_range(self,
                            az_duty_min: Optional[float]=None,
                            az_duty_max: Optional[float]=None,
                            el_duty_min: Optional[float]=None,
                            el_duty_max: Optional[float]=None) -> None:

        if az_duty_min is not None:
            await self._rpc(f"D- -a {az_duty_min:.2f}".encode("ascii"))

        if az_duty_max is not None:
            await self._rpc(f"D+ -a {az_duty_max:.2f}".encode("ascii"))

        if el_duty_min is not None:
            await self._rpc(f"D- -e {el_duty_min:.2f}".encode("ascii"))

        if el_duty_max is not None:
            await self._rpc(f"D+ -e {el_duty_max:.2f}".encode("ascii"))

    async def preaos(self) -> None:
        self.epoch = time.time_ns()

    async def aos(self) -> None:
        pass

    async def los(self) -> None:
        # TODO: implement parking position
        pass

    async def pop_motion_log(self):
        """
        Reads, resets and returns the motion log from the controller box. Call this function
        frequently enough to avoid log overflow.
        """
        if not self.mlog:
            self._open_mlog()

        ts = struct.pack('<Q', time.time_ns())
        sep = struct.pack('<fffff', math.nan, math.nan, math.nan, math.nan, math.nan)
        bytes = await self._rpc(b"L", binary_resp_end_seq=sep)
        if not bytes.endswith(sep):
            raise ControllerBoxError(f"Failed to read motion log, total bytes read: "
                                     f"{len(bytes)}, last 20 bytes: 0x{bytes[-20:].hex()}, "
                                     f"should have been 0x{sep.hex()}")
        self.mlog.write(ts)
        self.mlog.write(bytes)
        # self.mlog.flush()

    async def _rpc(self, cmd: bytes, binary_resp_end_seq=None) -> bytes:
        """
        Send a command to the controller box and return the response.

        Args:
            cmd: Command to send
        """
        async with self._lock:
            await self._write_command(cmd)
            if binary_resp_end_seq:
                return await self._read_bin_resp(binary_resp_end_seq)
            return await self._read_response()

    async def _write_command(self, cmd: bytes) -> None:
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
            self._writer.write(cmd)
            await self._writer.drain()

            if self.debug:
                self.dlog.write(f"{time.time()} WRITE: {cmd}\n")
                # self.dlog.flush()

        except serial.SerialTimeoutException as e:
            raise ControllerBoxError("Serial connection to controller box timed out: ", e)

        except Exception as e:
            raise ControllerBoxError("Communication error while writing to controller box: ", e) from e

    async def _read_response(self) -> bytes:
        """
        Read one line input of serial com.

        Returns:
            Received `bytes` from the controller box

        Raises:
            `ControllerBoxError` - in case the controller box encoutered an error.
        """
        while True:
            try:
                rsp = await self._reader.readline()

                if self.debug:
                    self.dlog.write(f"{time.time()} READ: {rsp}\n")
                    # self.dlog.flush()

            except Exception as e:
                raise ControllerBoxError(
                    f"Error while reading message from controller box: {e}"
                ) from e

            # Raise error if the line starts with "Error"
            if rsp.startswith(b"Error: "):
                if b"position cannot be sensed" in rsp:
                    if self.log is not None:
                        self.log.warning(rsp[7:].decode("ascii").strip())
                    continue
                raise ControllerBoxError(rsp[7:].decode("ascii").strip())
            break

        return rsp

    async def _read_bin_resp(self, end_seq: bytes) -> bytes:
        """
        Read until (and including) `end_seq` from the serial port.

        Returns:
            Received `bytes` from the controller box
        """
        rsp = b''
        while not rsp.endswith(end_seq):
            tmp = await self._reader.readuntil(end_seq)
            rsp += tmp
            if len(tmp) == 0:
                break
        return rsp

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

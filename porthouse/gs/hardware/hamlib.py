"""
Python interface class to connect Hamlib daemon via TCP socket

$ sudo apt-get install -y hamlib-utils
"""

import asyncio
import logging
import math
import time
from typing import Dict, List, Optional, Tuple, Union

from .base import PositionType, RotatorController, RotatorError

__all__ = [
    "HamlibError",
    # "HamlibRadioInterface",
    "HamlibController",
    "HamlibErrorString",
    "parse_address",
]


# https://github.com/Hamlib/Hamlib/blob/master/include/hamlib/rig.h#L119
HamlibErrorString: Dict[int, str] = {
    0: "No error",
    -1: "Invalid parameter",
    -2: "Invalid Configuration (serial,...)",
    -3: "Memory shortage",
    -4: "Function not implemented, but will be",
    -5: "Communication timed out",
    -6: "IO Error, including open failed",
    -7: "Internal Hamlib error",
    -8: "Protocol error",
    -9: "Command rejected by the rig/rot",
    -10: "Command performed, but arg truncated",
    -11: "Function not available",
    -12: "VFO not targetable",
    -13: "Error talking on the bus",
    -14: "Collision on the bus",
    -15: "NULL RIG handle or any invalid pointer parameter in get arg",
    -16: "Invalid VFO",
    -17: "Argument out of domain of func",
}


class HamlibError(RotatorError):
    """Exception class for errors returned by Hamlib or caused by the connection to it"""


def parse_address(address_str: str) -> Tuple[str, int]:
    """Convert the string "host:port" to the tuple (host, port)"""
    addr, port = address_str.rsplit(":", 1)
    return addr, int(port)


class HamlibController(RotatorController):
    """
    Controller class for a rotator behind a Hamlib daemon (rotctld)
    """

    def __init__(
        self,
        address: str,
        az_min: float = -180,
        az_max: float = 450,
        el_min: float = -5,
        el_max: float = 95,
        rotator_model: Optional[dict] = None,
        horizon_map_file: Optional[str] = None,
        min_sun_angle: Optional[float] = None,
        control_sw_version: int = 1,
        parking_position: Optional[Tuple[float, float]] = None,
        tracking_delay_s: float = 0.5,
        log: Optional[logging.Logger] = None,
        debug: bool = False,
        prefix: str = "",
    ) -> None:
        """
        Args:
            address: Address of rotctld, in the format "host:port"
        """
        super().__init__(
            address,
            az_min,
            az_max,
            el_min,
            el_max,
            rotator_model,
            horizon_map_file,
            min_sun_angle,
            control_sw_version,
            parking_position,
            tracking_delay_s,
            debug,
            log,
        )

        self.prefix = prefix
        self._timeout = 1.0
        self._target = parse_address(address)
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()

    async def setup(self) -> None:
        async with self._lock:
            await self._connect()
        await self.get_position()

    async def close(self) -> None:
        async with self._lock:
            await self._disconnect()

    async def stop(self) -> None:
        await self._execute(b"S\n")

    async def get_position(
        self, with_timestamp: bool = False
    ) -> Union[PositionType, Tuple[PositionType, float]]:
        t0 = time.time()
        res = await self._execute(b"p\n", data_lines=2)
        self.current_pos_ts = (t0 + time.time()) / 2.0
        self.current_position = HamlibController._parse_position_output(res)

        await self.maybe_enforce_limits()
        return (
            self.current_position
            if not with_timestamp
            else (self.current_position, self.current_pos_ts)
        )

    async def set_position(
        self,
        az: float,
        el: float,
        vel: Optional[Tuple[float, float]] = None,
        ts: Optional[float] = None,
        shortest_path: bool = True,
    ) -> None:
        self.position_valid(az, el, raise_error=True)
        self.target_position = (az, el)
        self.target_velocity = vel or (0.0, 0.0)
        self.target_pos_ts = ts or time.time()
        self.is_healthy = True
        self.shortest_path = shortest_path

        command_az = self._shortest_azimuth(az) if shortest_path else az
        await self._execute(f"P {command_az:.2f} {el:.2f}\n".encode("ascii"))

    async def get_position_target(
        self, get_vel: bool = False
    ) -> Union[PositionType, Tuple[PositionType, PositionType]]:
        if get_vel:
            return self.target_position, self.target_velocity
        return self.target_position

    async def get_position_range(self) -> Tuple[float, float, float, float]:
        return self.az_min, self.az_max, self.el_min, self.el_max

    async def set_position_range(
        self,
        az_min: Optional[float] = None,
        az_max: Optional[float] = None,
        el_min: Optional[float] = None,
        el_max: Optional[float] = None,
    ) -> Tuple[float, float, float, float]:
        if az_min is not None:
            self.az_min = az_min
        if az_max is not None:
            self.az_max = az_max
        if el_min is not None:
            self.el_min = el_min
        if el_max is not None:
            self.el_max = el_max
        return await self.get_position_range()

    async def reset_position(self, az: float, el: float) -> Tuple[float, float]:
        pass  # raise NotImplementedError("rotctld does not support reset_position")

    async def get_dutycycle_range(self) -> Tuple[float, float, float, float]:
        pass  # raise NotImplementedError("rotctld does not support duty cycle control")

    async def set_dutycycle_range(
        self,
        az_duty_min: Optional[float] = None,
        az_duty_max: Optional[float] = None,
        el_duty_min: Optional[float] = None,
        el_duty_max: Optional[float] = None,
    ) -> None:
        pass  # raise NotImplementedError("rotctld does not support duty cycle control")

    async def get_backlash(self) -> Tuple[float, float]:
        pass  # raise NotImplementedError("rotctld does not support backlash control")

    async def set_backlash(
        self,
        az_backlash: Optional[float] = None,
        el_backlash: Optional[float] = None,
    ) -> Tuple[float, float]:
        pass  # raise NotImplementedError("rotctld does not support backlash control")

    async def get_pid_coef(self, coef: str) -> Tuple[float, float]:
        pass  # raise NotImplementedError("rotctld does not support PID control")

    async def set_pid_coef(
        self,
        coef: str,
        az_coef: Optional[float] = None,
        el_coef: Optional[float] = None,
    ) -> Tuple[float, float]:
        pass  # raise NotImplementedError("rotctld does not support PID control")

    async def preaos(self) -> None:
        pass

    async def aos(self) -> None:
        pass

    async def los(self) -> None:
        if self.parking_position:
            await self.set_position(*self.parking_position, shortest_path=False)

    async def pop_motion_log(self) -> None:
        pass

    def _shortest_azimuth(self, az: float) -> float:
        """
        Return the azimuth, equal to az modulo 360, that is inside the allowed range
        and closest to the current azimuth.
        """
        current = self.current_position
        if current is None:
            return az
        k_min = math.ceil((self.az_min - az) / 360.0)
        k_max = math.floor((self.az_max - az) / 360.0)
        candidates = [az + 360.0 * k for k in range(k_min, k_max + 1)]
        return min(candidates, key=lambda c: abs(c - current[0]), default=az)

    async def _connect(self) -> None:
        host, port = self._target
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=self._timeout
            )
        except (OSError, asyncio.TimeoutError) as e:
            raise HamlibError(
                f"Cannot connect to rotctld at {host}:{port}"
            ) from e

    async def _disconnect(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _read_line(self, reader: asyncio.StreamReader) -> bytes:
        line = await asyncio.wait_for(reader.readline(), timeout=self._timeout)
        if not line:
            raise ConnectionResetError("rotctld closed the connection")
        return line

    async def _execute(self, command: bytes, data_lines: int = 0) -> bytes:
        """
        Send a command to rotctld and return the data lines of the response.

        Args:
            command: Command to send, with the final newline
            data_lines: Number of data lines that rotctld sends if the command succeeds

        Raises:
            `HamlibError` - if the connection fails or if rotctld returns an error code.
        """
        async with self._lock:
            if self._reader is None or self._writer is None:
                await self._connect()
            reader, writer = self._reader, self._writer
            if reader is None or writer is None:
                raise HamlibError("Not connected to rotctld")

            lines: List[bytes] = []
            try:
                writer.write(command)
                await asyncio.wait_for(writer.drain(), timeout=self._timeout)
                lines.append(await self._read_line(reader))
                if not lines[0].startswith(b"RPRT"):
                    for _ in range(data_lines - 1):
                        lines.append(await self._read_line(reader))
            except (OSError, asyncio.TimeoutError) as e:
                await self._disconnect()
                raise HamlibError(
                    "Failed to send to or receive from rotctld"
                ) from e

        if self.debug and self.log is not None:
            self.log.debug(f"rotctld write: {command!r}, read: {lines!r}")

        if lines[0].startswith(b"RPRT"):
            try:
                code = int(lines[0][4:])
            except ValueError as e:
                raise HamlibError(
                    f"Failed to cast return code to int: {lines[0]!r}"
                ) from e
            if code != 0:
                raise HamlibError(
                    HamlibErrorString.get(code, f"Unknown error {code}")
                )
            return b""
        return b"".join(lines)

    @staticmethod
    def _parse_position_output(output: bytes) -> PositionType:
        """
        Parse the response of the rotctld command "p".

        Expected input format: "<az>\\n<el>\\n"
        """
        try:
            az, el = (float(value) for value in output.decode("ascii").split())
        except ValueError as e:
            raise HamlibError(
                f"Failed to parse az/el information: {output!r}"
            ) from e
        return az, el

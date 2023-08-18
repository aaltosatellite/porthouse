"""
    Python interface class to connect Hamlib daemon via TCP socket

    $ sudo apt-get install -y hamlib-utils
"""

import socket
from typing import Optional, Tuple

from .base import RotatorError, RotatorController

__all__ = [
    "HamlibError",
    "HamlibRadioInterface",
    "HamlibController",
    "HamlibErrorString",
    "parse_address",
]


# Look up to decode hamlib error codes to strings
# https://github.com/Hamlib/Hamlib/blob/master/include/hamlib/rig.h#L119
HamlibErrorString = {
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
    -17: "Argument out of domain of func"
}


class HamlibError(RotatorError):
    """
    Exception class for errors returned by Hamlib
    """


def parse_address(address_str):
    """
    A util to parse address string to tuple.
    """
    addr, port = address_str.split(":")
    return addr, int(port)


class HamlibController(RotatorController):
    """
    Wrapper for Hamlib Rotator Interface
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._connected = False
        self._target = parse_address(self.address)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def connect(self):
        """
        Connect to hamlib daemon
        """
        try:
            self._sock.connect(self._target)
            self._connected = True
        except ConnectionRefusedError:
            raise
        except socket.error:
            raise
        return True

    def disconnect(self):
        """
            Disconnect from the hamlib daemon
        """
        self._sock.close()
        self._connected = False

    def stop(self):
        return self._execute(b"S\n")

    def set_position(self,
                     az, el,
                     rounding=1,
                     shortest_path=True):

        self.position_valid(az, el, raise_error=True)
        self.target_position = (az, el)

        if shortest_path:
            # TODO: Mimic sortest path
            pass

        return self._execute(f"P {round(az, rounding)} {round(el, rounding)}\n")

    def get_position(self):
        ret = self._execute(b"p\n")
        try:
            az, el = tuple(map(float, ret.decode("ascii").split()))
            self.current_position = az, el
        except ValueError:
            raise HamlibError("Failed to cast az/el information to floats")

        self.maybe_enforce_limits()
        return self.current_position

    def get_position_target(self):
        return self.target_position

    def get_position_range(self) -> Tuple[float, float, float, float]:
        return self.az_min, self.az_max, self.el_min, self.el_max

    def set_position_range(self,
                           az_min: Optional[float] = None,
                           az_max: Optional[float] = None,
                           el_min: Optional[float] = None,
                           el_max: Optional[float] = None,
                           rounding: int = 1) -> Tuple[float, float, float, float]:
        if az_min is not None:
            self.az_min = az_min
        if az_max is not None:
            self.az_max = az_max
        if el_min is not None:
            self.el_min = el_min
        if el_max is not None:
            self.el_max = el_max
        return self.get_position_range()

    def reset_position(self, az: float, el: float) -> None:
        raise NotImplementedError("reset_position not implemented")

    def get_dutycycle_range(self) -> Tuple[int, int, int, int]:
        pass

    def set_dutycycle_range(self, az_duty_min: Optional[int] = None, az_duty_max: Optional[int] = None,
                            el_duty_min: Optional[int] = None, el_duty_max: Optional[int] = None) -> None:
        pass

    def _execute(self, command):
        """
        Execute command
        """

        if not self._connected:
            self.connect()

        if isinstance(command, str):
            command = bytes(command, "ascii")

        # TODO: Timeout/disconnect
        try:
            self._sock.send(command)
            response = self._sock.recv(1024)
        except socket.error as e:
            raise HamlibError("Failed to send or recv") from e

        if self.debug:
            print("[rotctld ret: %r]" % response)

        if response.startswith(b"RPRT"):
            try:
                v = int(response[4:]) # Parse return code
            except ValueError:
                raise HamlibError("Failed to cast return code to int")

            if v != 0:
                raise HamlibError(HamlibErrorString.get(v, "Unknown error %d" % v))
        else:
            return response


class HamlibRadioInterface:
    """
    Wrapper for Hamlib Radio Interface
    """

    def __init__(self, addr, debug=False):
        """
        """
        self.target = parse_address(addr)
        self.connected = False
        self.debug = debug
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)


    def connect(self):
        """
        Connect to hamlib daemon
        """
        try:
            self._sock.connect(self.target)
            self.connected = True
        except socket.error:
            raise
        return True


    def execute(self, command):
        """
        Send command to daemon and wait for response
        """

        if not self.connected:
            print("HAMLIB not connected!")

        if isinstance(command, str):
            command = bytes(command, "ascii")

        if self.debug:
            print("[rotctld write: %r]" % command)

        # TODO: Timeout/disconnect
        try:
            self._sock.send(command)
            response = self._sock.recv(1024)
        except Exception as e: # FIXME:
            raise HamlibError("Socket error :(") from e

        if self.debug:
            print("[rotctld ret: %r]" % response)

        if response[:4] == b"RPRT":
            # Parse return code
            try:
                v = int(response[4:])
            except ValueError:
                raise HamlibError("Failed to cast return code to int")

            if v != 0:
                raise HamlibError(HamlibErrorString.get(v, "Unknown error %d" % v))
        else:
            return response


    def disconnect(self):
        """
            Disconnect from the hamlib daemon
        """
        self._sock.close()
        self.connected = False


    def set_vfo(self, vfo):
        """
        Set/select used VFO source
        """
        return self.execute(f"V {vfo}\n")


    def set_frequency(self, freq):
        """
        Set VFO frequency
        """
        return self.execute(f"F {freq}\n")


    def get_frequency(self):
        """
            Get current frequency
        """
        try:
            return int(self.execute("f\n"))
        except ValueError:
            raise HamlibError("Failed to cast getFrequency output to int")


    def set_mode(self, modulation, bandwidth):
        """
        Set mode
        """
        return self.execute(f"M {modulation} {bandwidth}\n")


    def get_mode(self):
        """
        Get mode
        """
        try:
            mode, passband = self.execute("m\n").split()
            return mode, int(passband)
        except ValueError:
            raise HamlibError("Failed to cast getMode output")


    def set_level(self, level, value):
        """
        Set level
        """
        return self.execute(f"L {level} {value}\n")


    def get_level(self, level):
        """
        Get a level reading from the radio
        PREAMP, ATT, VOX, AF, RF, SQL, RAWSTR, AF
        """
        try:
            return float(self.execute(f"l {level}\n"))
        except ValueError:
            raise HamlibError("Failed to cast getLevel() to int")


    def set_split_vfo(self, split_mode, vfo):
        """
            Sets split mode ON and TX VFO
            split_mode: 1 = ON, 0 = OFF
        """
        return self.execute(f"S {split_mode} {vfo}\n")


    def get_split_vfo(self):
        """
            Get Split VFO
        """
        try:
            split_mode, vfo = self.execute("s\n").split()
            return int(split_mode), vfo
        except ValueError:
            raise HamlibError("Failed to cast getSplitVFO() output")


    def set_split_frequency(self, freq):
        """
            Set Split Frequency for TX VFO
        """
        # doesn't work well with IC910H currently??
        return self.execute("I %d\n" % freq)


    def get_split_frequency(self):
        """
            Get split frequency
        """
        try:
            return int(self.execute("i\n"))
        except ValueError:
            raise HamlibError("Failed to cast getSplitFrequency() to int")


    def set_split_mode(self, modulation, bandwidth):
        """
            Set split mode
            sets modulation and bandwidth of TX VFO. Use 0 for default bandwidth
        """
        return self.execute(f"X {modulation} {bandwidth} %d\n")


    def get_split_mode(self):
        """
            Get split mode
        """
        try:
            modulation, bandwidth = self.execute("x\n").split()
            return modulation, int(bandwidth)
        except ValueError:
            raise HamlibError("Failed to cast getSplitMode() output")


    def set_repeater_shift(self, sign):
        """
            Set repeater shift
            sign can be "+", "-" or something else
        """
        return self.execute("R %s\n" % sign)


    def get_repeater_shift(self):
        """
            Get Repeater Shift
        """
        try:
            return int(self.execute("r\n"))
        except ValueError:
            raise HamlibError("Failed to cast getRepeaterShift() to int")


    def set_repeater_ffset(self, offset):
        """
            Set repeater offset
        """
        return self.execute("O %d\n" % offset)


    def get_repeater_offset(self):
        """
            Get repeater offset
        """
        try:
            return int(self.execute("o\n"))
        except ValueError:
            raise HamlibError("Failed to cast getRepeaterOffset() to int")


    def set_memory(self, number):
        """
        Set 'Memory#' channel number.
        """
        return self.execute("E %d\n" % number)


    def get_memory(self):
        """
        Get current memory channel
        """
        try:
            return int(self.execute("e\n"))
        except ValueError:
            raise HamlibError("Failed to cast getMemory() to int")


    def run_vfo_op(self, vfo_op):
        """
        Perform 'Mem/VFO Op'.

        Mem  VFO  operation is one of: CPY, XCHG, FROM_VFO, TO_VFO, MCL,
        UP, DOWN, BAND_UP, BAND_DOWN, LEFT, RIGHT, TUNE, TOGGLE.
        """
        return self.execute("G %s\n" % vfo_op)


    def memory_to_vfo(self):
        """
        Executes hamlib vfo_op command and transfers data from memory slot to active VFO
        """
        return self.run_vfo_op("TO_VFO")


    def vfo_to_memory(self):
        """
        """
        return self.run_vfo_op("FROM_VFO")

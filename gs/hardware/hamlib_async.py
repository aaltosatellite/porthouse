"""
    Python interface class to connect Hamlib daemon via TCP socket

    $ sudo apt-get install -y hamlib-utils
"""
import asyncio

__all__ = [
    "HamlibError",
    "rotctl"
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

class HamlibError(RuntimeError):
    """
    Exception class for errors returned by Hamlib
    """


def parse_address(address_str):
    """
    A util to parse address string to tuple.
    """
    addr, port = address_str.split(":")
    return addr, int(port)


class rotctl:
    """
    Wrapper for Hamlib Rotator Interface
    """

    def __init__(self, addr="localhost:4533", debug=False):
        """
        """
        self.connected = False
        self.reader = None
        self.writer = None
        self.target = parse_address(addr)
        self.target_position = (0, 0)
        self.debug = debug


    async def connect(self):
        """
        Connect to hamlib daemon
        """
        self.reader, self.writer = \
            await asyncio.open_connection(self.target[0], self.target[1])


    async def execute(self, command):
        """
        Execute command
        """

        if self.writer is None:
            await self.connect()

        if isinstance(command, str):
            command = bytes(command, "ascii")

        if self.debug:
            print("[rotctld write: %r]" % command)

        # TODO: Timeout/disconnect
        try:
            self.writer.write(command)
            await self.writer.drain()
            response = await self.reader.read(1024)
        except Exception as e:
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


    async def disconnect(self):
        """
        Disconnect from the hamlib daemon
        """

        self.writer.close()
        await self.writer.wait_closed()

        self.writer, self.reader = None, None


    async def stop(self):
        """
        Stop rotator movement
        """
        return await self.execute(b"S\n")


    async def set_position(self,
                     az, el,
                     rounding=1,
                     shortest_path=True):
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

        """
        self.target_position = (az, el)
        await self.execute(f"P {round(az, rounding)} {round(el, rounding)}\n")

        return await self.get_position()


    async def get_position(self):
        """
            Request rotator's current position and return it as tuple
        """
        ret = await self.execute(b"p\n")
        try:
            return tuple(map(float, ret.decode("ascii").split()))
        except ValueError:
            raise HamlibError("Failed to cast az/el information to floats")


    async def get_position_target(self):
        """
        Get position where the rotator is moving to.
        """
        await asyncio.sleep(0) # Just to make the function to a coroutine
        return self.target_position

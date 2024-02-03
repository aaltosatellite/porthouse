"""
    Python interface class to connect Hamlib daemon via TCP socket

    $ sudo apt-get install -y hamlib-utils
"""
import asyncio

__all__ = [
    "HamlibAsyncController"
]

from porthouse.gs.hardware.hamlib import HamlibController, HamlibError, HamlibErrorString, parse_address


class HamlibAsyncController(HamlibController):
    """
    Wrapper for Hamlib Rotator Interface
    """

    def __init__(self, *args, **kwargs):
        super(HamlibController, self).__init__(*args, **kwargs)
        self._connected = False
        self._target = parse_address(self.address)
        self._reader = None
        self._writer = None

    async def connect(self):
        """
        Connect to hamlib daemon
        """
        self._reader, self._writer = await asyncio.open_connection(self._target[0], self._target[1])

    async def disconnect(self):
        """
        Disconnect from the hamlib daemon
        """

        self._writer.close()
        await self._writer.wait_closed()

        self._writer, self._reader = None, None

    async def stop(self):
        return await self._execute_async(b"S\n")

    async def set_position(self,
                     az, el,
                     rounding=1,
                     shortest_path=True):

        self.position_valid(az, el, raise_error=True)
        self.target_position = (az, el)

        if shortest_path:
            # TODO: Mimic sortest path
            pass

        await self._execute_async(f"P {round(az, rounding)} {round(el, rounding)}\n")

        return await self.get_position()

    async def get_position(self):
        ret = await self._execute_async(b"p\n")
        try:
            az, el = tuple(map(float, ret.decode("ascii").split()))
            self.current_position = az, el
        except ValueError:
            raise HamlibError("Failed to cast az/el information to floats")

        await self.maybe_enforce_limits()
        return self.current_position

    async def maybe_enforce_limits(self) -> None:
        # async version of base class maybe_enforce_limits
        if self.enforce_limits and not self.position_valid(*self.current_position):
            trg_pos = await self.get_position_target()
            if not self.position_valid(*trg_pos):
                await self.set_position(*self.closest_valid_position(*trg_pos), rounding=1, shortest_path=True)

    async def get_position_target(self):
        await asyncio.sleep(0)  # Just to make the function to a coroutine
        return self.target_position

    async def _execute_async(self, command):
        if self._writer is None:
            await self.connect()

        if isinstance(command, str):
            command = bytes(command, "ascii")

        if self.debug:
            print("[rotctld write: %r]" % command)

        # TODO: Timeout/disconnect
        try:
            self._writer.write(command)
            await self._writer.drain()
            response = await self._reader.read(1024)
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

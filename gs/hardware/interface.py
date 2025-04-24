from porthouse.core.rpc_async import send_rpc_request


class RotatorInterface:
    """
    Rotator control related commands
    """

    def __init__(self, prefix):
        self.prefix = prefix

    async def status(
            self,
            verbose: bool=True
        ):
        """
        Get rotator status.
        """
        status = await send_rpc_request("rotator", f"{self.prefix}.rpc.status")
        if verbose:
            print(status)
        else:
            return status

    async def move(
            self,
            az: float,
            el: float,
            shortest: bool = True
        ):
        """
        Move the rotator to given azimuth-elevation position.

        Args:
            az: Target azimuth angle
            el: Target elevation angle
            shortest: If true, the shortest path is used.
        """
        await send_rpc_request("rotator", f"{self.prefix}.rpc.rotate", {
            "az": az, "el": el, "shortest": shortest
        })

    async def adjust(self, d_az: float, d_el: float):
        """
        Adjust position temporarily by given azimuth-elevation deltas.

        Args:
            d_az: Delta azimuth angle
            d_el: Delta elevation angle
        """
        await send_rpc_request("rotator", f"{self.prefix}.rpc.adjust", {
            "d_az": d_az, "d_el": d_el
        })

    async def reset_position(
            self,
            az: float,
            el: float
        ):
        """
        Reset position to given values without moving the rotator. If new position is outside allowed range,
        the rotator will be moved to the closest allowed position.

        Args:
            az: Target azimuth angle
            el: Target elevation angle
        """
        await send_rpc_request("rotator", f"{self.prefix}.rpc.reset_position", {
            "az": az, "el": el
        }, timeout=5)

    async def stop(self):
        """
        Stop rotator immediately.
        """
        await send_rpc_request("rotator", f"{self.prefix}.rpc.stop")

    async def set_tracking(
            self,
            enabled: bool=True
        ):
        """
        Enable/disable automatic tracking.

        Args:
            enabled: If true automatic tracking is enabled.
        """
        await send_rpc_request("rotator", f"{self.prefix}.rpc.tracking", {
            "mode": "automatic" if enabled else "manual"
        })

    async def get_position_range(self):
        """
        Get allowed position range.
        """
        return await send_rpc_request("rotator", f"{self.prefix}.rpc.get_position_range")

    async def set_position_range(self, az_min: float, az_max: float, el_min: float, el_max: float):
        """
        Set allowed position range.
        """
        return await send_rpc_request("rotator", f"{self.prefix}.rpc.set_position_range", {
            "az_min": az_min,
            "az_max": az_max,
            "el_min": el_min,
            "el_max": el_max,
        }, timeout=5)

    async def get_dutycycle_range(self):
        """
        Get allowed duty cycle range.
        """
        return await send_rpc_request("rotator", f"{self.prefix}.rpc.get_dutycycle_range")

    async def set_dutycycle_range(self, az_min: float, az_max: float, el_min: float, el_max: float):
        """
        Set allowed duty cycle range.
        """
        return await send_rpc_request("rotator", f"{self.prefix}.rpc.set_dutycycle_range", {
            "az_min": az_min,
            "az_max": az_max,
            "el_min": el_min,
            "el_max": el_max,
        }, timeout=5)

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
            el: float
        ):
        """
        Move the rotator to given azimuth-elevation position.

        Args:
            az: Target azimuth angle
            el: Target elevation angle
        """
        await send_rpc_request("rotator", f"{self.prefix}.rpc.rotate", {
            "az": az, "el": el
        })


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


from porthouse.core.rpc_async import send_rpc_request


class OrbitTrackerInterface:
    """
    Satellite tracking related commands
    """


    async def status(self, verbose=True):
        """
        Get satellite tracker status.
        """
        status = await send_rpc_request("tracking", "orbit.rpc.status")
        if verbose:
            print(status)
        else:
            return status


    async def set_target(
            self,
            satellite: str
        ):
        """
        Set the satellite to be tracked.

        Args:
        """
        await send_rpc_request("tracking", "orbit.rpc.set_target", {
            "satellite": satellite
        })


    async def get_satellites(self, verbose=True):
        """
            Get list of all possible
        """
        satellites = await send_rpc_request("tracking", "tle.rpc.get_tle")
        if verbose:
            for sat in satellites["tle"]:
                print(sat["name"])
        else:
            return satellites



    async def update_tle(self):
        """
        Trigger TLE update routine
        """
        await send_rpc_request("tracking", "tle.rpc.update")


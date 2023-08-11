from typing import List

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

    async def add_target(
            self,
            target: str,
            rotators: List[str],
            preaos_time: int = 120,
        ):
        """
        Add target satellite to be tracked by the given rotators.

        Args:
            target: Name of the target satellite
            rotators: List of rotators to be used for tracking
            preaos_time: Time in seconds to start tracking before the pass
        """
        params = {
            "target": target,
            "rotators": rotators,
        }
        if preaos_time is not None:
            params["preaos_time"] = preaos_time
        await send_rpc_request("tracking", "orbit.rpc.add_target", params)

    async def remove_target(
            self,
            target: str,
            rotators: List[str]
        ):
        """
        Stop tracking target satellite with the given rotators.

        Args:
            target: Name of the target satellite
            rotators: List of rotators used for tracking
        """
        await send_rpc_request("tracking", "orbit.rpc.remove_target", {
            "target": target,
            "rotators": rotators,
        })

    async def get_satellites(self, verbose=True):
        """
            Get list of all possible target satellites
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

    async def ephem_status(self, verbose=True):
        """
        Get celestial object tracker status.
        """
        status = await send_rpc_request("tracking", "ephem.rpc.status")
        if verbose:
            print(status)
        else:
            return status

    async def ephem_add_target(
            self,
            target: str,
            rotators: List[str]
        ):
        """
        Add target celestial object to be tracked by the given rotators.

        Args:
            target: target celestial object specified in the format "Moon", "de440s.bsp/Sun", "HIP/12345",
                    or "34.7/23.4" [RA/DEC]
            rotators: List of rotators to be used for tracking
        """
        await send_rpc_request("tracking", "ephem.rpc.add_target", {
            "target": target,
            "rotators": rotators,
        })

    async def ephem_remove_target(
            self,
            target: str,
            rotators: List[str]
        ):
        """
        Stop tracking target celestial object with the given rotators.

        Args:
            target: Target celestial object specification
            rotators: List of rotators used for tracking
        """
        await send_rpc_request("tracking", "ephem.rpc.remove_target", {
            "target": target,
            "rotators": rotators,
        })

    async def gnss_status(self, verbose=True):
        """
        Get GNSS object tracker status.
        """
        status = await send_rpc_request("tracking", "gnss.rpc.status")
        if verbose:
            print(status)
        else:
            return status

    async def gnss_add_target(
            self,
            target: str,
            rotators: List[str]
        ):
        """
        Add target GNSS-tracked object to be tracked by the given rotators.

        Args:
            target: target GNSS-tracked object specified in the format "call-sign" [APRS call-sign],
                    or "34.7/23.4/500.2" [LAT/LON/ALT[m]]
            rotators: List of rotators to be used for tracking
        """
        await send_rpc_request("tracking", "gnss.rpc.add_target", {
            "target": target,
            "rotators": rotators,
        })

    async def gnss_remove_target(
            self,
            target: str,
            rotators: List[str]
        ):
        """
        Stop tracking target GNSS-tracked object with the given rotators.

        Args:
            target: Target GNSS-tracked object specification
            rotators: List of rotators used for tracking
        """
        await send_rpc_request("tracking", "gnss.rpc.remove_target", {
            "target": target,
            "rotators": rotators,
        })

    async def module_status(self, module: str, verbose=True):
        """
        Get status of the given tracker module.
        Args:
            module: Prefix of the tracking module
        """
        status = await send_rpc_request("tracking", f"{module}.rpc.status")
        if verbose:
            print(status)
        else:
            return status

    async def module_add_target(
            self,
            module: str,
            target: str,
            rotators: List[str]
        ):
        """
        Add target to be tracked using the given module and by the given rotators.

        Args:
            module: Prefix of the tracking module to be used
            target: Target object to be tracked by the given module
            rotators: List of rotators to be used for tracking
        """
        await send_rpc_request("tracking", f"{module}.rpc.add_target", {
            "target": target,
            "rotators": rotators,
        })

    async def module_remove_target(
            self,
            module: str,
            target: str,
            rotators: List[str]
        ):
        """
        Stop tracking target using the given module and with the given rotators.

        Args:
            module: Prefix of the tracking module to be used
            target: Target GNSS-tracked object specification
            rotators: List of rotators used for tracking
        """
        await send_rpc_request("tracking", f"{module}.rpc.remove_target", {
            "target": target,
            "rotators": rotators,
        })

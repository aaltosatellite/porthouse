from datetime import datetime
from porthouse.core.rpc_async import send_rpc_request


class Rotator:
    """
    Rotator control related commands
    """

    @staticmethod
    async def status(
            verbose: bool=True
        ):
        """
        Get rotator status.
        """
        status = await send_rpc_request("rotator", "uhf.rpc.status")
        if verbose:
            print(status)
        else:
            return status


    @staticmethod
    async def move(
            az: float,
            el: float
        ):
        """
        Move the rotator to given azimith-elevation position.

        Args:
            az: Target azimuth angle
            el: Target elevation angle
        """
        await send_rpc_request("rotator", "uhf.rpc.rotate", {
            "az": az, "el": el
        })


    @staticmethod
    async def stop():
        """
        Stop rotator immidiately.
        """
        await send_rpc_request("rotator", "uhf.rpc.stop")


    @staticmethod
    async def set_tracking(
            enabled: bool=True
        ):
        """
        Enable/disable automatic tracking.

        Args:
            enabled: If true automatic tracking is enable.
        """
        await send_rpc_request("rotator", "uhf.rpc.tracking", {
            "mode": "automatic" if enabled else "manual"
        })


class Tracker:
    """
    Satellite tracking related commands
    """

    @staticmethod
    async def status(verbose=True):
        """
        Get rotator status.
        """
        status = await send_rpc_request("tracker", "rpc.status")
        if verbose:
            print(status)
        else:
            return status


    @staticmethod
    async def set_target(
            satellite: str
        ):
        """
        Set the satellite to be tracked.

        Args:
        """
        await send_rpc_request("tracker", "orbit.rpc.set_target", {
            "satellite": satellite
        })


    @staticmethod
    async def get_satellites(verbose=True):
        """
            Get list of all possible
        """
        satellites = await send_rpc_request("tracking", "tle.rpc.get_tle")
        if verbose:
            for sat in satellites["tle"]:
                print(sat["name"])
        else:
            return satellites


    @staticmethod
    async def update_tle():
        """
        Trigger TLE update routine
        """
        await send_rpc_request("tracking", "tle.rpc.update")



async def log():
    """
        Get latest log messages
    """
    for line in send_rpc_request("log", "rpc.get_history", {}).get("entries", []):
        line["created"] = datetime.fromtimestamp(line["created"]).strftime('%Y-%m-%d %H:%M:%S')
        print("{created} - {module} - {level} - {message}".format(**line))

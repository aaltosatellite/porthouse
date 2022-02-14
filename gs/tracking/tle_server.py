"""

    TLE Server module maintains a system wide list of tracked satellites and
    updates provides uptodate TLE orbital elements from various source.

    Module provides a RPC interface for requesting the satellite list and updating the list.

    different TLE source types are:
    - *lines*: static lines from any source. Specify 'tle1' and 'tle2' parameters
    - *web*: txt on a HTTP. Specify 'websrc' and 'identifier' parameters.
    - *space-track*: request TLE from space-track.org using NORAD ID

    To modify the satellite list edit "tle.cfg" file and re-run TLE update routine.

    TODO:
    - Add JSON-OMM support

    Dependencies:
    $ pip3 install requests-async
"""

import time
import json
import asyncio
import yaml
from datetime import datetime
from typing import Any, Dict, Optional, NoReturn

import skyfield.api as skyfield
import requests_async as requests

from porthouse.core.config import cfg_path
from porthouse.core.basemodule_async import BaseModule, RPCError, rpc, queue, bind


class InvalidTLE(Exception):
    pass


def validate_tle(tle1: str, tle2: str) -> bool:
    """
    Validate TLE-lines aka check that

    Args:
        entry: TLE entry as dict.

    Returns:
        A boolean wheather the TLE was valid or not.
    """
    try:
        sc = skyfield.EarthSatellite(tle1, tle2)
        return True
    except ValueError as exc:
        raise InvalidTLE(f"{tle1!r}, {tle2!r}") from exc
    return False



class TLEServer(BaseModule):
    """
        Fetches TLE parameters from varioous sources defined in the cfg file
    """

    def __init__(self,
            cfg_file: Optional[str]=None,
            **kwarg
        ):
        """
        Initialize module
        """
        super().__init__(**kwarg)

        self.credentials = None
        self.tle_data = {}
        self.config_file = cfg_file or cfg_path("tle.yaml")
        self.updating = False

        # Load old TLE cache which will be server before update has been completed
        try:
            with cfg_path(".tle_cache", "r") as f:
                self.tle_data = json.loads(f.read())
        except:
            #self.log.warning("Failed to read .tle-cache", exc_info=True)
            pass

        # Parse TLE configuration file
        tle_cfg = yaml.load(open(self.config_file, "r"), Loader=yaml.Loader)
        self.update_interval: int = tle_cfg.get("update_interval", 12 * 3600) # seconds

        # Read space-track.org credentials from cfg file
        if "space-track_credentials" in tle_cfg:
            self.credentials = {
                "identity": tle_cfg["space-track_credentials"]["identity"],
                "password": tle_cfg["space-track_credentials"]["password"],
            }


        # Create TLE updater task
        asyncio.get_event_loop().create_task(self.updater_task())


    @rpc()
    @bind("tracking", "tle.rpc.#")
    def rpc_handler(self,
            request_name: str,
            request_data: Dict[str, Any]
        ):
        """
        RPC callback
        """

        if request_name == "tle.rpc.update":
            """
            # Start TLE updating

            Call returns immidiately and updating will happend on the background.
            """

            self.log.debug("TLE Update request received")

            if not self.updating:

                # Create new task for immediate update
                asyncio.get_event_loop().create_task(self.update_tles())


        elif request_name == "tle.rpc.get_tle":
            """
            # Request satellite/TLE list

            If satellites name is provided only the requested TLE lines are returned.

            If 'check_time' argument is provided with client's local UNIX timestamp
            the server will check the time synchronization and alert if server and
            client are out of time sync.
            """

            # If client's local time is provided check it to make sure
            # orbit propagation calculations will in sync.
            if "check_time" in request_data:
                diff = abs(request_data["check_time"] - time.time())
                if diff > 2.0:
                    raise RPCError(f"TLE server and client are out of sync! " \
                                   f"System clock difference {diff} s")

            if "satellite" in request_data:
                # Filter by given satellite name
                for tle in self.tle_data:
                    if tle["name"] == request_data["satellite"]:
                        return {
                            "time": datetime.utcnow().isoformat(' '),
                            "name": tle["name"],
                            "tle1": tle["tle1"],
                            "tle2": tle["tle2"],
                        }
                raise RPCError("No such satellite")

            # Return all TLE lines
            return {
                "time": datetime.utcnow().isoformat(' '),
                "tle": self.tle_data
            }

        else:
            raise RPCError("Unknown command")


    async def updater_task(self) -> NoReturn:
        """
        Infinitely running async task to update
        """
        await asyncio.sleep(1)

        while True:

            try:
                # Catch all errors to prevent network error or such to crash the auto updater
                await self.update_tles()
                await asyncio.sleep(self.update_interval)

            except:
                self.log.error("TLE update process failed", exc_info=True)
                await asyncio.sleep(3600)


    async def update_tles(self) -> None:
        """
        Update all TLE lines
        """

        # Simple lock to prevent parallel update processes issued by RPC
        if self.updating:
            return
        self.updating = True

        self.log.debug("Updating TLEs")

        # Make a dict of the TLE list for updating process
        new_tle = { tle["name"]: tle for tle in self.tle_data }

        auth_cookies = None
        webcache = {}

        # Try to reload configuration file
        try:
            tle_cfg = yaml.load(open(self.config_file, "r"), Loader=yaml.Loader)
        except (yaml.parser.ParserError, FileNotFoundError):
            self.log.error("Failed to parse TLE configuration file!", exc_info=True)
            return

        # Foreach satellite
        for satellite in tle_cfg.get("satellites", []):

            try:
                source = satellite.get("source")
                if source == "web":
                    #
                    # Static file over HTTP/GET
                    #

                    # Download TLE source from the web (use cache if possible)
                    weburl = satellite["websrc"]
                    if weburl in webcache:
                        response = webcache[weburl]
                    else:
                        try:
                            self.log.debug("Downloading %s", weburl)
                            response = await requests.get(weburl, timeout=3)

                        except requests.RequestException as e:
                            self.log.error("Failed to download file %r: %s", weburl, e, exc_info=True)
                            continue

                        if response.status_code == 200:
                            response = response.text.split("\r\n")
                            webcache[weburl] = response
                        else:
                            raise ValueError(f"Error with {weburl!r}!\r\n{r.text}")

                    tle_iter = response.__iter__()

                    if satellite.get("identifier", None):
                        try:
                            # Iterate until correct line is found
                            ident = satellite["identifier"]
                            while tle_iter.__next__().strip() != ident:
                                pass
                        except StopIteration:
                            self.log.error("Unable to find TLE entry for %s from the response!", satellite)

                    else:
                        # No identifier provided so just ake first first two lines
                        pass

                    entry = {
                        "name": satellite,
                        "tle1": tle_iter.__next__().strip(),
                        "tle2": tle_iter.__next__().strip(),
                    }

                    if validate_tle(entry["tle1"], entry["tle2"]):
                        new_tle[satellite.get("name")] = entry

                elif source == "space-track":
                    #
                    # Space-track
                    #

                    if self.credentials is None:
                        self.log.error("No login credential provided fo space-track.org")
                        continue

                    if auth_cookies is None:
                        # Login to space-track.org
                        r = await requests.post("https://www.space-track.org/ajaxauth/login",
                            data=self.credentials,
                            timeout=3)
                        auth_cookies = r.cookies

                    # Request latest TLE entry for given NORAD ID
                    URL = "https://www.space-track.org/basicspacedata/query/class/tle_latest/" \
                        "NORAD_CAT_ID/{id}/orderby/EPOCH%20desc/limit/1/format/tle"

                    try:
                        r = await requests.get(URL.format(id=satellite["norad_id"]),
                            cookies=auth_cookies, timeout=3)
                    except requests.RequestException as e:
                        self.log.error("Failed to query TLE from space-track.org: %r", e)
                        continue

                    if r.status_code == 200:
                        lines = r.text.split("\n")
                        entry = {
                            "name": satellite,
                            "tle1": lines[0],
                            "tle2": lines[1]
                        }
                    else:
                        self.log.error("space-track.org responded HTTP error %d: %r",
                            r.status_code, r.text)
                        continue

                    if validate_tle(entry["tle1"], entry["tle2"]):
                        new_tle[satellite.get("name")] = entry


                elif source == "lines":
                    #
                    # Static TLE lines
                    #

                    entry = {
                        "name": satellite,
                        "tle1": satellite["tle1"],
                        "tle2": satellite["tle2"],
                    }

                    if validate_tle(entry["tle1"], entry["tle2"]):
                        new_tle[satellite.get("name")] = entry


                else:
                    self.log.error(f"Invalid TLE source {source!r} for {satellite!r}")

            except InvalidTLE:
                self.log.error(f"TLE lines for {e!r} does not conform to TLE format")

            except KeyError as e:
                self.log.error(f"Missing parameter {e.args!r} for satellite {satellite!r}")

            except:
                self.log.error("Unknown error while updating the TLE", exc_info=True)

        # Otherwise update TLE list and make a list out of the dict
        self.tle_data = list(new_tle.values())

        # Dump the cache
        with open(cfg_path(".tle_cache"), "w") as f:
            f.write(json.dumps(self.tle_data))

        self.log.info("TLE updated!")
        self.updating = False

        # Broadcasting the new TLE lines
        await self.publish({
            "time": datetime.utcnow().isoformat(' '),
            "tle": self.tle_data
        }, exchange="tracking", routing_key="tle.updated")


if __name__ == "__main__":
    #from porthouse.launcher import Launcher
    #Launcher('TLEserver')
    TLEServer(
        cfg_file="tle.cfg",
        amqp_url="amqp://guest:guest@localhost:5672/",
        debug=True
    ).run()

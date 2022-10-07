"""
    Orbit tracker
"""

import json
import asyncio
import yaml
import datetime
from enum import IntEnum
from typing import Optional, NoReturn

import skyfield

from porthouse.core.config import cfg_path
from porthouse.core.basemodule_async import BaseModule, RPCError, RPCRequestError, rpc, queue, bind

from .utils import Satellite, Pass

ts = skyfield.api.load.timescale()


class TrackerStatus(IntEnum):
    """ Tracker states """
    DISABLED = 0
    WAITING = 1
    AOS = 2
    TRACKING = 3
    LOS = 4


class OrbitTracker(BaseModule):
    """ Module class to implement OrbitTracker. """

    def __init__(self, **kwarg):
        """
        Initialize module.
        """
        BaseModule.__init__(self, debug=True, **kwarg)

        self.target = None
        self.mode = TrackerStatus.DISABLED
        self.satellites = []

        # Open config file
        with open(cfg_path("groundstation.yaml")) as f:
            self.gs_config = yaml.load(f, Loader=yaml.Loader)['groundstation']

        # Create observer from config file
        self.gs = skyfield.api.Topos(
            latitude=skyfield.api.Angle(degrees=self.gs_config["latitude"]),
            longitude=skyfield.api.Angle(degrees=self.gs_config["longitude"]),
            elevation_m=self.gs_config["elevation"]
        )

        self.preaos_duration = datetime.timedelta(seconds=120)

        loop = asyncio.get_event_loop()
        loop.create_task(self.setup(self.gs_config.get("default", None)))


    async def setup(self, default_target: Optional[str]) -> NoReturn:
        """
        """
        await asyncio.sleep(5)
        await self.set_target(default_target)

        while True:
            if self.target:
                await self.update_tracking()
            await self.broadcast_status()
            await asyncio.sleep(2)


    @rpc()
    @bind("tracking", "orbit.rpc.#")
    async def rpc_handler(self,
            request_name: str,
            request_data: dict):
        """
        Handle RPC commands
        """
        request_name = request_name[6:]
        # Change active spacecraft
        if request_name == "rpc.set_target":
            #
            # Set the target
            #
            await self.set_target(request_data["satellite"])

        elif request_name == "rpc.get_config":
            #
            #
            #

            return {
                "target": self.obs_name,
                "lat": self.obs.lat,
                "lon": self.obs.long,
                "elevation": self.obs.elevation,
                "date": self.obs.date,
                "pressure": self.obs.pressure,
                "horizon": self.obs.horizon,
            }

        elif request_name == "rpc.get_satellite_pass":
            #
            #
            #

            satellite = self.get_satellite(request_data["satellite"])

            if satellite is None:
                return None

            if "period" in request_data:
                self.predict_passes(satellite, request_data["period"])

                passes = []
                for sc_pass in satellite.passes:
                    passes.append(sc_pass.to_dict())
            else:
                self.predict_passes(satellite)
                passes = satellite.get_next_pass().to_dict()

            if "avoid" in request_data:
                if isinstance(request_data["avoid"], str):
                    request_data["avoid"] = [request_data["avoid"]]

                avoid_passes = []
                for sat in request_data["avoid"]:
                    avoid_sat = self.get_satellite(sat)
                    if "period" in request_data:
                        self.predict_passes(avoid_sat, request_data["period"])
                    else:
                        self.predict_passes(avoid_sat)
                    avoid_passes.extend(avoid_sat.passes)

                collission_free_passes = []
                for sc_pass in satellite.passes:
                    overlap_free = True
                    for avoid_pass in avoid_passes:
                        if sc_pass.check_overlap(avoid_pass):
                            overlap_free = False
                            break

                    if overlap_free:
                        collission_free_passes.append(sc_pass.to_dict())

                passes = collission_free_passes

            return passes

        elif request_name == "rpc.get_satellite_position":
            satellite = self.get_satellite(request_data["satellite"])

            if satellite is None:
                return None

            return self.target.to_dict()

            self.update_satellite_position(satellite)
            pos = (self.target.sc - self.gs).at(ts.now())


            pos = {}
            pos.update(self.get_satellite_ground_position(satellite))
            pos.update(self.get_satellite_sky_position(satellite))

            return pos

        elif request_name == "rpc.get_satellite_period":
            satellite = self.get_satellite(request_data["satellite"])

            if satellite is None:
                return None

            period = 24 * 60 / satellite.sc._n
            return {"period": period}

        elif request_name == "rpc.get_schedule":
            satellite = self.get_satellite(request_data["satellite"])

            if satellite is None:
                return None

            if "period" in request_data:
                self.predict_passes(satellite, request_data["period"])
            else:
                self.predict_passes(satellite)

        else:
            raise RPCError(f"No such command {request_name}")


    @queue()
    @bind("tracking", "tle.updated")
    def tle_updated_callback(self, msg: dict) -> None:
        """
        Receive new TLEs from the TLEServer
        """
        return

        try: # Try to parse TLE
            msg_body = json.loads(msg.body)
        except ValueError:
            return

        # Clear the whole list and recreate satellite objects
        for tle_data in msg_body["tle"]:

            self.log.debug("%s TLE updated!", tle_data["name"])

            sat = Satellite(tle_data["name"], tle_data["tle1"], tle_data["tle2"])
            self.calculate_passes(self.gs)
            self.satellites.append(sat)


    async def update_tracking(self) -> None:
        """
        Update tracking calculations
        """

        #
        await asyncio.sleep(0)

        # Update current prediction
        now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
        pos: skyfield.positionlib.Geometric = (self.target.sc - self.gs).at(ts.now())


        next_pass = self.target.get_next_pass()
        if next_pass is None:
            self.log.critical("No passes!")
            self.mode = TrackerStatus.DISABLED

        # Tracking state machine:
        if self.mode == TrackerStatus.WAITING:

            if self.debug:
                s = (next_pass.t_aos - now).total_seconds()
                m, s = divmod(s, 60)
                h, m = divmod(m, 60)

                if h > 0:
                    self.log.debug("AOS in %d hour and %d minutes", h, m)
                else:
                    self.log.debug("AOS in %d minutes and %d seconds", m, s)

            # Check if a pass is already going on
            pos = (self.target.sc - self.gs).at(ts.now())
            if pos.altaz()[0].degrees > 0:
                await self.send_event("aos", target=self.target.name)
                self.mode = TrackerStatus.TRACKING

            # Is AOS about to happen?
            elif now >= next_pass.t_aos - self.preaos_duration:

                await self.send_event("preaos", **next_pass.to_dict())
                self.mode = TrackerStatus.AOS


        elif self.mode == TrackerStatus.AOS:

            # Is the satellite over the horizon
            pos = (self.target.sc - self.gs).at(ts.now())
            if pos.altaz()[0].degrees > 0: # Above the horizon?
                await self.send_event("aos", target=self.target.name)
                self.mode = TrackerStatus.TRACKING

            elif self.debug:
                sec = (next_pass.t_aos - now).total_seconds()
                self.log.debug("AOS in %d seconds", sec)


        elif self.mode == TrackerStatus.TRACKING:

            # Calculate the postion in 2 seconds in future
            now += datetime.timedelta(seconds=1)

            pos = (self.target.sc - self.gs).at(ts.from_datetime(now))
            el, az, range, _, _, range_rate = pos.frame_latlon_and_rates(self.gs)

            if self.debug:
                m, s = divmod((next_pass.t_los - now).total_seconds(), 60)
                self.log.debug("Tracking %s, LOS in %d minutes %d seconds", self.target.name, m, s)

            # Broadcast spacecraft position
            await self.broadcast_pointing(az=az.degrees, el=el.degrees, range=range.m, range_rate=range_rate.m_per_s)

            # Is the satellite below the horizon
            if pos.altaz()[0].degrees < 0:
                await self.send_event("los", target=self.target.name)
                self.mode = TrackerStatus.LOS

        elif self.mode == TrackerStatus.LOS:
            #
            # Handle LOS
            #
            self.log.debug("After LOS")

            if False:
                # Every sc pass is only tracked once so no unnecessary tracking
                await self.set_target(None)
            else:
                self.mode = TrackerStatus.WAITING
                self.target.calculate_passes(self.gs)


    async def broadcast_pointing(self, az: float, el: float, range: float, range_rate: float) -> None:
        """
        Broadcast pointing information

        Args:
            az: Target azimuth
            el: Target elevation
            range: Target velocity
            range_rate:
        """

        if el < 0:
            el = 0
        if az > 180:
            az -= 360

        await self.publish({
            "target": self.target.name,
            "az": round(az, 2),
            "el": round(el, 2),
            "range": round(range, 2),
            "range_rate": round(range_rate, 2)
        }, exchange="tracking", routing_key="target.position")


    async def broadcast_status(self) -> None:
        """
        Broadcast tracker status
        """

        status_message = {}

        # Do we have target which has upcoming passes
        if self.target is not None and len(self.target.passes) > 0:

            if self.mode == TrackerStatus.AOS:
                status = f"Pre-AOS for {self.target.name}"
                pass_info = self.target.passes[0]
            elif self.mode == TrackerStatus.TRACKING:
                status = f"Tracking {self.target.name}"
                pass_info = self.target.passes[0]
            elif self.mode == TrackerStatus.DISABLED:
                status = "Disabled"
                pass_info = None
            else:
                status = f"Waiting for {self.target.name}"
                pass_info = self.target.passes[0]

            if pass_info is not None:
                pass_info = pass_info.to_dict()

            status_message = {
                "satellite": self.target.name,
                "pass": pass_info,
                "status": status,
            }

        else:
            status_message = {
                "satellite": None,
                "pass": None,
                "status": "No target"
            }

        #self.log.debug("Status: %r", status_message)
        await self.publish(status_message,
            exchange="tracking",
            routing_key="tracker.status")


    async def send_event(self, event_name, **params):
        """
        Send event
        """

        self.log.info("%s event omited: %s", event_name, params)
        await self.publish(params, exchange="event", routing_key=event_name)


    async def set_target(self, satellite: Optional[str]=None):
        """
        Set tracking target
        """

        await asyncio.sleep(0) # Make sure that something is awaited.

        if self.mode == TrackerStatus.TRACKING:
            await self.send_event("los", satellite=self.target.name)
        self.mode = TrackerStatus.DISABLED
        self.target = None

        if satellite is None:
            return 
        
        self.log.info("Changing target to %s", satellite)

        try:
            self.log.debug("Requesting TLE for %s", satellite)
            ret = await self.send_rpc_request("tracking", "tle.rpc.get_tle", {
                "satellite": satellite
            })

        except RPCRequestError as e:
            self.log.error("Failed to request TLE: %s", e.args[0])
            return

        self.target = Satellite(satellite, ret["tle1"], ret["tle2"])

        # Check TLE age
        utcnow = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
        tle_age = utcnow - self.target.sc.epoch.utc_datetime()
        if tle_age.days > 14:
            self.log.warning("TLE lines for \"%s\" are %.1f days old and might be inaccurate!",
                satellite, tle_age.days)

        self.target.calculate_passes(self.gs)
        await self.send_event("next_pass", **self.target.get_next_pass().to_dict())
        self.mode = TrackerStatus.WAITING


    def get_satellite(self, satellite):
        """Returns ephem spacecraft if satellite is in list else None."""
        if satellite == "None":
            return None
        else:
            for sat in self.satellites:
                if sat.name == satellite:
                    return sat
            self.log.error("Satellite %s not in list!", satellite)
            return None


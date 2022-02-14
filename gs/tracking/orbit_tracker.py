"""
    Orbit tracker module
"""

import json
import math
import yaml
import asyncio
from enum import Enum
from datetime import datetime
from typing import Any, Dict, Optional

import skyfield.api as skyfield

from porthouse.core.config import cfg_path
from porthouse.core.basemodule_async import BaseModule, RPCError, RPCRequestError, rpc, queue, bind

from .utils import Satellite, Pass


class TrackerStatus(Enum):
    """ Tracker states """
    DISABLED = 0
    WAITING = 1
    AOS = 2
    TRACKING = 3
    LOS = 4


class OrbitTracker(BaseModule):
    """ Module class to implement OrbitTracker.  """

    def __init__(self, **kwarg):
        """
        Initialize module.

        """
        BaseModule.__init__(self, **kwarg)
        self.target = None
        self.mode = TrackerStatus.DISABLED

        # Open config file
        cfg = yaml.load(open(cfg_path("groundstation.yaml"), "r"), Loader=yaml.Loader)

        # Create observer from config file
        observer_cfg: Dict[str, Any] = cfg["observer"]
        self.gs_name = cfg.get("observer", "name")
        self.horizon = math.radians(observer_cfg.get("horizon", 0.0))
        self.gs = skyfield.Topos(
            latitude=skyfield.Angle(degrees=float(observer_cfg.get("latitude"))),
            longitude=skyfield.Angle(degrees=float(observer_cfg.get("latitude"))),
            elevation_m=float(observer_cfg.get("elevation"))
        )

        # Finish the setup in coroutine
        loop = asyncio.get_event_loop()
        loop.create_task(self.setup(cfg.get("default")))


    async def setup(self, default_target: str) -> None:
        """
        Coroutine for finishing the module setup
        """

        if default_target is not None:
            await self.set_target(default_target)

        while True:
            if self.target:
                await self.update_traking()
            await self.broadcast_status()
            await asyncio.sleep(2)


    @rpc()
    @bind("tracking", "rpc.#")
    async def rpc_handler(self,
            request_name: str,
            request_data: Dict[str, Any],
        ) -> Optional[Dict[str, Any]]:
        """
        Handle RPC commands
        """

        if request_name == "rpc.set_target":
            #
            # Set the target satellite
            #
            await self.set_target(request_data["satellite"])

        elif request_name == "rpc.get_config":
            #
            # Return
            #
            return {
                "name": self.gs_name,
                "lat": self.gs.latitude.degrees,
                "lon": self.gs.longitude.degrees,
                "elevation": self.gs.elevation.m,
                "horizon": self.horizon,
                "target": self.target.name
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

            self.update_satellite_position(satellite)

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
            raise RPCError("No such command")


    @queue()
    @bind("tracking", "tle.updated")
    def tle_updated_callback(self, msg):
        """
        Receive new TLEs from the TLEServer
        """

        try: # Try to parse TLE
            msg_body = json.loads(msg.body)
        except ValueError:
            return

        # No target to be update
        if self.target is None:
            return

        # Find the TLE lines for our target
        new_tle = next(filter(lambda tle: tle["name"] == self.target.name, msg_body["tle"]), None)
        if new_tle is not None:
            self.log.debug("%s TLE updated!", self.target.name)

            sat = Satellite(new_tle["name"], new_tle["name"], new_tle["tle1"], new_tle["tle2"])
            sat.sc.compute(self.obs)


    async def update_traking(self):
        """
        Update tracking calculations
        """

        # Update current prediction
        pos = (self.target - self.gs).at(ts.now()).altaz()

        next_pass = self.target.get_next_pass()
        if next_pass is None:
            self.log.critical("No passes!")
            self.mode = TrackerStatus.DISABLED
        else:
            tr, azr, tt, azt, altt, ts, azs = next_pass.params

        # Tracking state machine:
        if self.mode == TrackerStatus.WAITING:

            if self.debug:
                delta = ephem.localtime(tr) - ts.now()
                sec = delta.seconds + 24 * 60 * delta.days

                m, s = divmod(sec, 60)
                h, m = divmod(m, 60)

                if h > 0:
                    self.log.debug("AOS in %d hour and %d minutes", h, m)
                else:
                    self.log.debug("AOS in %d minutes and %d seconds", m, s)

            # Check if a pass is already going on
            if self.target.sc.alt > 0:

                self.send_event("aos", satellite=self.target.name)
                self.mode = TrackerStatus.TRACKING

            # Is AOS about to happen?
            elif now + 120 * ephem.second >= tr:

                self.send_event("preaos", satellite=self.target.name,
                                aos=int(ephem.localtime(tr).strftime("%s")),
                                aos_az=math.degrees(azr),
                                maximum=int(ephem.localtime(tt).strftime("%s")),
                                maximum_az=math.degrees(azt),
                                maximum_el=math.degrees(altt),
                                los=int(ephem.localtime(ts).strftime("%s")),
                                los_az=math.degrees(azs))
                self.mode = TrackerStatus.AOS

        elif self.mode == TrackerStatus.AOS:

            # Is the satellite over the horizon
            if self.target.sc.alt > 0:

                self.send_event("aos", satellite=self.target.name)
                self.mode = TrackerStatus.TRACKING

            elif self.debug:

                delta = ephem.localtime(tr) - ephem.localtime(now)
                sec = delta.seconds + 24 * 60 * delta.days

                self.log.debug("AOS in %d seconds", sec)

        elif self.mode == TrackerStatus.TRACKING:

            self.obs.date = now + 1.5 * ephem.second
            self.target.sc.compute(self.obs)

            self.obs.date = now + 1.5 * ephem.second
            self.target.sc.compute(self.obs)

            # Print debug stuff
            if self.debug:
                delta = ephem.localtime(ts) - ephem.localtime(now)
                sec = delta.seconds + 24 * 60 * delta.days
                m, s = divmod(sec, 60)

                self.log.debug(
                    "Tracking %s, LOS in %d minutes %d seconds", self.target.name, m, s)

            # Broadcast spacecraft position
            await self.broadcast_pointing(
                az=math.degrees(self.target.sc.az),
                el=math.degrees(self.target.sc.alt),
                vel=self.target.sc.range_velocity
            )

            # Is the satellite below the horizon
            if self.target.sc.alt < 0:
                self.send_event("los", satellite=self.target.name)
                self.mode = TrackerStatus.LOS

        elif self.mode == TrackerStatus.LOS:
            # Handle LOS
            self.log.debug("After LOS")

            # Every sc pass is only tracked once so no unnecessary tracking
            self.set_target("None")

        await asyncio.sleep(0)


    async def broadcast_pointing(self, az, el, vel):
        """
        Broadcast pointing information

        Args:
            az: Target azimuth
            el: Target elevation
            vel: Target velocity
        """

        if el < 0:
            el = 0
        if az > 180:
            az -= 360

        await self.publish({
            "target": self.target.name,
            "az": round(az, 1),
            "el": round(el, 1),
            "velocity": round(vel, 1)
        }, exchange="tracking", routing_key="target.position")


    async def broadcast_status(self):
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
                "status": "No target"
            }

        self.log.debug("Status: %r", status_message)
        await self.publish(status_message,
            exchange="tracking",
            routing_key="tracker.status")


    async def send_event(self, event_name, **params):
        """
        Send event
        """

        self.log.info("%s event omited: %s", event_name, params)
        await self.publish(params, exchange="event", routing_key=event_name)


    async def set_target(self, satellite: Optional[str]) -> None:
        """
        Set tracking target.

        Args:

        """

        if self.mode == TrackerStatus.TRACKING:
            await self.send_event("los", satellite=self.target.name)

        self.log.info("Changing target to %s", satellite)

        try:
            await self.update_tle(satellite)
        except KeyError:
            self.log.error("No TLE information for satellite %s", satellite)
            return

        self.mode = TrackerStatus.DISABLED

        try:
            # Reset target and check whether new target is in satellites list
            self.target = self.get_satellite(satellite)

            if self.target is None:
                self.log.debug("Target set to None!")
                return

            self.target.sc.compute(self.obs)
            self.predict_passes(self.target)

            self.mode = TrackerStatus.WAITING

            # Check TLE epoch
            tle_age = ephem.now() - self.target.sc._epoch

            if tle_age > 30:
                self.log.warning("TLE lines for \"%s\" are %.1f days old and might be inaccurate!",
                    satellite, tle_age)

        except ValueError as e:
            # If no passes were found
            self.log.error("%s: %s", satellite, e.args[0])


    async def update_tle(self, target):
        """
            Read latest TLE lines from the TLE configuration file.
        """

        # If "None" target is selected, tracking shall be disabled
        if target == "None":
            self.target = None
            return

        try:
            self.log.debug("Requesting TLE for %s", target)
            ret = await self.send_rpc_request("tracking", "tle.rpc.get_tle", {
                "satellite": target
            })

        except RPCRequestError as e:
            self.log.error("Failed to request TLE: %s", e.args[0])
            return

        sc = self.get_satellite(target)

        for satellite in ret["tle"]:
            if satellite["name"] == target:
                sc.tle0 = satellite["name"]
                sc.tle1 = satellite["tle1"]
                sc.tle2 = satellite["tle2"]
                return

        self.log.critical("No avaible for target satellite!")


    def predict_passes(self, satellite, prediction_period=24.0):
        """
            Predict upcoming passes of satellite w.r.t. to ground station.
        """
        startTime = ephem.now()
        self.obs.date = startTime

        satellite.passes = []

        satellite.sc.compute(self.obs)

        # If a pass has already started go little bit back in time.
        if satellite.sc.alt > 0:
            self.obs.date -= 15 * ephem.minute
            satellite.sc.compute(self.obs)

        # Calculate passes for the given prediction period
        while self.obs.date < ephem.Date(startTime + prediction_period * ephem.hour):

            try:
                tr, _, tt, _, ts, _ = next_pass = self.obs.next_pass(satellite.sc)

                if tr == None:
                    raise ValueError

                # Calculate azimuth at max elevation
                self.obs.date = tt
                satellite.sc.compute(self.obs)
                next_pass = (next_pass[0], next_pass[1], next_pass[2],
                             satellite.sc.az, next_pass[3], next_pass[4], next_pass[5])

                newpass = Pass(satellite.name, next_pass)
                satellite.passes.append(newpass)

            except ValueError:
                ts = ephem.Date(self.obs.date + ephem.hour)

            self.obs.date = ephem.Date(ts + 0.1 * ephem.hour)

        # Make sure we have some kind of result
        if len(satellite.passes) == 0:
            self.mode = TrackerStatus.DISABLED
            self.log.warning("No future passes were found for %s!", satellite.name)
            return

        # Pick pass parameters
        tr, _, tt, _, altt, ts, _ = satellite.passes[0].params

        # Construct info message
        msg = "Next pass for %s (Orbit %d)" % (
            satellite.name, satellite.sc._orbit)
        msg += ", AOS: %s" % ephem.localtime(tr).strftime("%Y-%m-%d %H:%M:%S")
        msg += ", LOS: %s" % ephem.localtime(ts).strftime("%Y-%m-%d %H:%M:%S")
        msg += ", Pass length: %s" % (ephem.localtime(ts) -
                                      ephem.localtime(tr))
        msg += ", Maximum elevation: %d degrees" % math.degrees(altt)
        self.log.info(msg)

        if self.debug:
            print("--------------------------------------------------------------")
            print("      Date/Time        Elev/Azim    Alt     Range     RVel    ")
            print("--------------------------------------------------------------")

            self.obs.date = tr

            while self.obs.date <= ts:
                satellite.sc.compute(self.obs)

                print("{0} | {1:4.1f} {2:5.1f} | {3:5.1f} | {4:6.1f} | {5:+7.1f}".format(
                    ephem.localtime(self.obs.date).strftime(
                        "%Y-%m-%d %H:%M:%S"),
                    math.degrees(satellite.sc.alt),
                    math.degrees(satellite.sc.az),
                    satellite.sc.elevation/1000.,
                    satellite.sc.range/1000.,
                    satellite.sc.range_velocity))

                self.obs.date = ephem.Date(self.obs.date + 20 * ephem.second)


    def get_satellite(self, satellite):
        """ Returns ephem spacecraft if satellite is in list else None. """
        if satellite == "None":
            return None
        else:
            for sat in self.satellites:
                if sat.name == satellite:
                    return sat
            self.log.error("Satellite %s not in list!", satellite)
            return None


    def update_satellite_position(self, satellite):
        """ Calculates position of satellite. """
        self.obs.date = ephem.now()
        satellite.sc.compute(self.obs)


    def get_satellite_ground_position(self, satellite):
        """ Returns position of satellite projected on ground. """
        lat = math.degrees(satellite.sc.sublat)
        lon = math.degrees(satellite.sc.sublong)
        alt = satellite.sc.elevation

        return {"lat": lat, "lon": lon, "alt": alt}

    def get_satellite_sky_position(self, satellite):
        """ Returns position of satellite in the sky. """
        az = math.degrees(satellite.sc.az)
        el = math.degrees(satellite.sc.alt)

        return {"az": az, "el": el}


if __name__ == "__main__":
    OrbitTracker(
        cfg_file="tracker.cfg",
        amqp_url="amqp://guest:guest@localhost:5672/",
        debug=True
    ).run()

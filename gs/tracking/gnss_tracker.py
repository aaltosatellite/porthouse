"""
    Tracking module for antenna tracking based on GPS-positions.
"""

import json
import math
import time
import asyncio
import yaml
import aiormq.abc
from typing import Dict, List, NoReturn, Optional, Tuple, NamedTuple

from porthouse.core.config import cfg_path
from porthouse.core.frame import Frame
from porthouse.core.basemodule_async import BaseModule, queue, bind


class GPSPosition(NamedTuple):
    latitude: float # in degrees
    longitude: float # in degrees
    altitude: float # in meter


class PointTracker(BaseModule):
    TRACKER_TYPE = "gnss"

    def __init__(self,
            observer: Optional[Dict]=None,
            callsigns: Optional[List[str]]=None,
            predict_movement: bool=False,
            **kwargs):
        """
        Initialize module
        """
        BaseModule.__init__(self, **kwargs)

        self.predict_movement = predict_movement
        self.previous_positions = []

        self.callsigns = [c.strip("-") for c in callsigns ]

        if observer is None:
            # Parse observer information from tracker's configuration file
            tracker_cfg = yaml.load(open(cfg_path("tracker.yaml"), "r"), Loader=yaml.Loader)
            observer = tracker_cfg["observer"]

        self.observer = GPSPosition(observer["latitude"], observer["longitude"], observer.get("elevation", 0))

        if predict_movement:
            task = asyncio.create_task(self.predict_task(), name="gnss_tracker.predict_task")
            task.add_done_callback(self.task_done_handler)

    def is_interesting_callsign(self, callsign: str) -> bool:
        """
        Check whether APRS callsign is in the list
        """

        callsign = callsign.split("-")
        for c in self.callsigns:
            try:
                if callsign[0] == c[0] and (len(c) == 1 or c[1] == callsign[1]):
                    return True
            except IndexError:
                pass

        return False


    @queue()
    #@bind("transport", "downlink")
    async def received_aprs_frame(self, msg: aiormq.abc.DeliveredMessage) -> None:
        """
        New frame received parse position data.
        """

        frame = Frame.from_json(msg.body)
        packet = frame # TODO:  decode

        if "addresses" in packet and not self.is_interesting_callsign(packet.addresses[0]):
            return

        if "lon" in packet and "lat" in packet:

            target = GPSPosition(packet["lat"], packet["lon"], packet.get("alt", 0))
            self.previous_positions.append((time.time(), target))

            if self.predict_movement:
                az, el = calculate_azimuth_elevation(self.observer, target)
                await self.set_pointing(az, el)


    @queue()
    @bind("tracking", "new_position")
    async def new_target_position(self, msg: aiormq.abc.DeliveredMessage) -> None:
        """
        """

        try:
            msg_body = json.loads(msg.body)
        except:
            self.log.error("Received invalid JSON: %r", msg.body, exc_info=True)
            return

        target = (msg_body["lat"], msg_body["lon"], msg_body.get("alt", 0))
        self.previous_positions.append((time.time(), target))

        if self.predict_movement:
            az, el = calculate_azimuth_elevation(self.observer, target)
            await self.set_pointing(az, el)


    async def predict_task(self) -> NoReturn:
        """
        Task for calculating
        """

        while True:

            await asyncio.sleep(2)

            if len(self.previous_positions) < 2:
                continue

            # Get data for interpolation
            time_a, pos_a = self.previous_positions[-2]
            time_b, pos_b = self.previous_positions[-1]
            delta_t = time_b - time_a

            time_passed: float = time.time() - time_b
            if time_passed < 1 and time_passed > 5*60:

                #

                az, el = calculate_azimuth_elevation(self.observer, pos_b)

            else:
                # Try to extrapolate position

                # Too sparse data points
                if delta_t > 5 * 60:
                    continue

                # Calculate the position in 1 second in the future
                time_passed += 1

                # Linear extrapolate
                lat = pos_b.latitude + time_passed * (pos_b.latitude - pos_a.latitude) / delta_t
                lon = pos_b.longitude + time_passed * (pos_b.longitude - pos_a.longitude) / delta_t
                alt = pos_b.altitude + time_passed * (pos_b.altitude - pos_a.altitude) / delta_t

                az, el = calculate_azimuth_elevation(self.observer, GPSPosition(lat, lon, alt))

            await self.set_pointing(az, el)
            #await self.broadcast_status()


    async def set_pointing(self, az: float, el: float) -> None:
        """
        Send pointing command to rotators

        Args:
            az: Target azimuth in degrees
            el: Target elevation in degrees
        """

        if el < 0:
            el = 0
        if az > 180:
            az -= 360

        await self.publish({
            "az": round(az, 1),
            "el": round(el, 1)
        }, exchange="tracking", routing_key="target.position")


    async def broadcast_status(self) -> None:
        """
        Broadcast tracker status
        """

        track_time, track_pos = None, None
        if len(self.previous_positions) > 1: # TODO: Not too old
            track_time, track_pos = self.previous_positions[-1]

        await self.publish({
            "position": track_pos,
            "last_update": track_time
        }, exchange="tracking", routing_key="tracker.status")




def calculate_azimuth_elevation(pointA: GPSPosition, pointB: GPSPosition) -> Tuple[float, float]:
    """
    Calculates the azimouth(bearing) and elevation between two points.

    The formulae used for azimuth (or bearing) is the following:
    θ = atan2(sin(Δlong).cos(lat2),
    cos(lat1).sin(lat2) − sin(lat1).cos(lat2).cos(Δlong))

    Args:
        pointA: The Position-tuple representing the latitude/longitude/height for the
            first point. Latitude and longitude must be in decimal degrees and height in meters
        pointB: The Position-tuple representing the latitude/longitude/height for the
            second point. Latitude and longitude must be in decimal degrees and height in meters

    Returns:
        A tuple containning the azimuth and elevation angles in degrees

    Remarks:
        Borrowed from: https://github.com/satnogs/satnogs-software/blob/master/luftballon/luftballon.py
        Authored by manthos and azisi. All praise and blame on them ;)
    """


    # assuming spherical earth with radius 6,367,000m
    R = 6367000
    lat1 = math.radians(pointA.latitude)
    lon1 = math.radians(pointA.longitude)
    lat2 = math.radians(pointB.latitude)
    lon2 = math.radians(pointB.longitude)

    diffLat = math.radians(pointB.latitude - pointA.latitude)
    diffLong = math.radians(pointB.longitude - pointA.longitude)

    x = math.sin(diffLong) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - \
       (math.sin(lat1) * math.cos(lat2) * math.cos(diffLong))

    initial_bearing = math.degrees(math.atan2(x, y))

    # Now we have the initial bearing but math.atan2 return values
    # from -180° to + 180° which is not what we want for a compass bearing
    # The solution is to normalize the initial bearing as shown below
    # initial_bearing = math.degrees(initial_bearing)

    azimuth = (initial_bearing + 360) % 360

    # calculations for elevation

    # calculations to fint the angle theta, between the 2 vectors
    # starting from the center of the earth pointing to base and target
    a = math.sin(diffLat / 2) ** 2 + math.cos(lat1) * \
        math.cos(lat2) * math.sin(diffLong / 2) ** 2
    theta = 2 * math.asin(math.sqrt(a))

    hBase = R + pointA.altitude
    hTarget = R + pointB.altitude
    phi = math.pi - theta - \
        math.atan((hBase * math.sin(theta)) /
                  (hTarget - hBase * math.cos(theta)))
    elevation = math.degrees(phi) - 90

    # return calculated azimuth and alt
    return azimuth, elevation


if __name__ == "__main__":
    from porthouse.launcher import Launcher
    #Launcher(PointTracker)
    PointTracker(
        amqp_url="amqp://guest:guest@localhost:5672/",
        debug=True
    ).run()

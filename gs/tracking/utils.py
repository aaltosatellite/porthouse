
from enum import IntEnum
from datetime import datetime, timedelta, timezone
from typing import Union, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor
import yaml

import numpy as np

from skyfield import searchlib
from skyfield import vectorlib
from skyfield.data import hipparcos
from skyfield.positionlib import position_of_radec, Geometric
import skyfield.api as skyfield

from porthouse.core.config import cfg_path
from porthouse.core.basemodule_async import RPCRequestError

ts = skyfield.load.timescale()


class PassStatus(IntEnum):
    """ Tracker states """
    DISABLED = 0
    WAITING = 1
    AOS = 2
    TRACKING = 3
    LOS = 4


class Pass:
    """
    Class to store and handle pass information
    """

    def __init__(self,
            name: str,
            gs: str,
            t_aos: datetime, az_aos: float,
            t_max: datetime, el_max: float, az_max: float,
            t_los: datetime, az_los: float,
            orb_no: int = None, status: PassStatus = PassStatus.WAITING):
        """ Initialize pass """
        self.name = name
        self.gs = gs
        self.status = status

        self.t_aos = t_aos
        self.az_aos = az_aos
        self.t_max = t_max
        self.el_max = el_max
        self.az_max = az_max
        self.t_los = t_los
        self.az_los = az_los

        self.orb_no = orb_no

    def __str__(self):
        """ Return Pass data as a string. """
        return f"Pass {self.name} for {self.gs} " \
               f"(AOS: {self.t_aos.isoformat()}, LOS: {self.t_los.isoformat()})"

    def to_dict(self):
        """Turns satellite pass values into a dict."""
        info = {
            "name": self.name,
            "gs": self.gs,
            "status": self.status.name,
            "t_aos": self.t_aos.isoformat(),
            "az_aos": self.az_aos,
            "el_max": self.el_max,
            "az_max": self.az_max,
            "t_los": self.t_los.isoformat(),
            "az_los": self.az_los,
            "elevation": self.el_max
        }
        if self.orb_no is not None:
            info["orb_no"] = self.orb_no
        return info

    @classmethod
    def from_dict(cls, entry: dict):
        """ Parse a Pass from a dict. """
        return cls(
            name=entry["name"],
            gs=entry["gs"],
            status=PassStatus[entry["status"]],
            t_aos=datetime.fromisoformat(entry["aos"]),
            az_aos=entry["az_aos"],
            el_max=entry["el_max"],
            az_max=entry["az_max"],
            t_los=datetime.fromisoformat(entry["los"]),
            az_los=entry["az_los"],
            orb_no=entry.get("orb_no", None)
        )

    def is_future(self):
        return datetime.utcnow() < self.t_aos

    def is_current(self):
        return self.t_aos < datetime.utcnow() < self.t_los

    def has_passed(self):
        return datetime.utcnow() > self.t_los

    def is_valid(self):
        """ Checks if the pass los is after aos. """
        return self.t_los > self.t_aos

    def __gt__(self, other):
        return self.t_aos > self.t_aos

    def __lt__(self, other):
        return self.t_aos < self.t_aos

    def is_inside(self, other: 'Pass'):
        """ Checks if self is inside other pass. """
        return not self.is_outside(other)

    def is_outside(self, other: 'Pass'):
        """ Checks if self is outside other pass. """
        return (self.t_aos <= other.t_los) and (self.t_los >= other.t_aos)

    def is_reaching_into(self, other: 'Pass'):
        """ Checks if self begins before and ends inside other pass. """
        # AOS overlap
        return self.t_aos < other.t_aos < self.t_los

    def is_reaching_out(self, other: 'Pass'):
        """ Checks if self begins inside and ends after other pass. """
        # LOS overlap
        return self.t_aos < other.t_los < self.t_los


class Satellite:
    """ Class to store satellite info """

    def __init__(self, name: str, tle1: str, tle2: str, gs: skyfield.Topos = None):
        """ Initialize satellite object """
        self.name = name
        self.tle1 = tle1
        self.tle2 = tle2
        self.gs = gs

        self.sc = skyfield.EarthSatellite(self.tle1, self.tle2)
        self.passes = []
        self.passes_start_time = None
        self.passes_end_time = None

    def __str__(self):
        """ Return string to describing the satellite object"""
        return f"Satellite ({self.name})"

    @property
    def target_name(self):
        return self.name

    @property
    def tle_age_days(self):
        utcnow = datetime.utcnow().replace(tzinfo=timezone.utc)
        tle_age = utcnow - self.sc.epoch.utc_datetime()
        return tle_age.days

    def pos_at(self, time: Union[None, str, datetime, skyfield.Time]) -> Geometric:
        return (self.sc - self.gs).at(parse_time(time))

    def to_dict(self, tle: bool=False):
        """
        """

        now = ts.now()

        sc = {
            "name": self.name,
        }

        if True and self.gs:
            pos = self.pos_at(now)
            el, az, range, _, _, range_rate = pos.frame_latlon_and_rates(self.gs)

            sc.update({
                "elevation": el.degrees,
                "azimuth": az.degrees,
                "range": range.km,
                "range_rate": range_rate.m_per_s
            })

        if False:
            #
            geocentric = self.sc.at(ts.utc(now.utc_datetime()))
            lat, lon = wgs84.latlon_of(geocentric)
            alt = wgs84.height_of(geocentric)

            sc.update({
                "latitude":  lat.degrees,
                "longitude": lon.degrees,
                "altitude": alt.km,
            })

        if True:
            sc["next_pass"] = self.passes[0].to_dict() if len(self.passes) else None

        if True:
            sc["passes"] = [p.to_dict() for p in self.passes]

        if tle:
            sc["tle1"] = self.tle1
            sc["tle2"] = self.tle2

        return sc

    def get_next_pass(self):
        """ Return next pass or None """
        return self.passes[0] if len(self.passes) else None

    def passes_contain(self, start_time, end_time=None, period=24):
        start_time = parse_time(start_time).utc_datetime()
        end_time = parse_time(end_time) if end_time is not None else start_time + timedelta(hours=period)
        return self.passes is not None and len(self.passes) > 0 and \
            self.passes_start_time <= start_time and self.passes_end_time >= end_time

    def calculate_passes(self, start_time: Union[None, str, datetime, skyfield.Time] = None,
                         end_time: Union[None, str, datetime, skyfield.Time] = None, period: float = 24,
                         min_elevation: float = 0, min_max_elevation: float = 0, sun_max_elevation: float = None,
                         sunlit: bool = None) -> list[Pass]:
        """
        Calculate passes for the satellite.

        Args:
            start_time:         start time for pass calculation, defaults to now
            period:             how many hours to calculate the passes for, defaults to 24 hours
            end_time:           if specified, overrides the period
            min_elevation:      minimum value for the maximum elevation for the pass to be considered valid
            min_max_elevation:  horizon to use for the calculation, defaults to 0
            sun_max_elevation:  maximum elevation of the sun for the pass to be considered valid, default=None
            sunlit:             if True, only calculate passes when the satellite is sunlit, default=None
        """
        # start time for pass calculation
        start_time = parse_time(start_time)
        end_time = parse_time(end_time) if end_time is not None else start_time + timedelta(hours=period)

        # Check if the satellite is already at the sky
        el, _, _ = self.pos_at(start_time).altaz()
        if el.degrees > min_elevation:
            start_time -= timedelta(minutes=30)

        if sunlit is None and sun_max_elevation is None:
            # Find all the events for the satellite, as before
            t_event, events = self.sc.find_events(self.gs, start_time, end_time, min_elevation)
        else:
            # Use own version of find_events that takes into account sunlit and sun_max_elevation params
            if CelestialObject.EARTH is None:
                CelestialObject.init_bodies()
            obj_gs = (CelestialObject.EARTH + self.sc) - (CelestialObject.EARTH + self.gs)
            t_event, events = find_events(obj_gs, start_time, end_time, min_elevation, min_max_elevation,
                                          CelestialObject.BODIES, sun_max_elevation, sunlit)

        self.passes = events_to_passes(self.name, self.sc - self.gs, t_event, events, min_max_elevation)
        self.passes_start_time = start_time.utc_datetime()
        self.passes_end_time = end_time.utc_datetime()
        return self.passes


class CelestialObject:
    BODIES = None
    EARTH = None

    """ Class to store celestial object info """
    (TYPE_STAR, TYPE_SSB, TYPE_RA_DEC) = range(3)

    TARGET_NAME_PREFIX = "cel:"

    @staticmethod
    def is_class_of(target_name: str):
        return target_name.startswith(CelestialObject.TARGET_NAME_PREFIX)

    def __init__(self, target: str, gs: skyfield.Topos = None):
        """
        Initialize CelestialObject
            target: target specification, e.g. "Moon", "de440s.bsp/Sun", "HIP/87937", "34.7/23.4" [ra/dec]
            gs: groundstation object
        """

        self.target = target
        self.gs = gs

        self.file = None
        self.earth = None
        self.obj = None
        self.ra = None
        self.dec = None
        self._initialized = False
        self.passes = []
        self.passes_start_time = None
        self.passes_end_time = None

        assert CelestialObject.is_class_of(target), f'Invalid target specs: {target}'
        parts = target[len(CelestialObject.TARGET_NAME_PREFIX):].split("/")

        if len(parts) == 1:
            # target is a major solar system body
            self.name = parts[0]
            self.type = self.TYPE_SSB
        elif len(parts) == 2:
            if parts[0] == 'HIP':
                # target is a star
                self.name = parts[1]
                self.type = self.TYPE_STAR
            else:
                try:
                    # target is a right ascension / declination pair
                    self.ra, self.dec = map(float, parts)
                    self.name = f"{self.ra}/{self.dec}"
                    self.type = self.TYPE_RA_DEC
                except ValueError:
                    # target is some sort of solar system body or spacecraft
                    self.file = parts[0]
                    self.name = parts[1]
                    self.type = self.TYPE_SSB
        else:
            assert False, f"Invalid target specification: {target}"

    @property
    def target_name(self):
        return self.target

    def pos_at(self, time: Union[None, str, datetime, skyfield.Time]) -> Geometric:
        assert self._initialized, "CelestialObject not initialized"
        return (self.obj - (self.earth + self.gs)).at(parse_time(time))

    @staticmethod
    def init_bodies():
        CelestialObject.BODIES = skyfield.load('de440s.bsp')
        CelestialObject.EARTH = CelestialObject.BODIES['Earth']

    def initialize(self):
        if CelestialObject.BODIES is None:
            self.init_bodies()
        self.earth = CelestialObject.EARTH

        if self.type == self.TYPE_SSB:
            try:
                if self.file:
                    bodies = skyfield.load(self.file)
                    if 'Earth' in bodies:
                        self.earth = bodies['Earth']
                else:
                    bodies = CelestialObject.BODIES
                self.obj = bodies[self.name]
            except ValueError as e:
                try:
                    from skyfield.jpllib import SpiceKernel
                    # TODO: fix this, e.g. where would the kernels be located?
                    kernel = SpiceKernel(self.file)
                    self.obj = kernel[self.name]
                except ValueError as e:
                    raise ValueError(f"Failed to open file {self.file} for target {self.target}")

        elif self.type == self.TYPE_STAR:
            # NOTE: requires pandas
            with skyfield.load.open(hipparcos.URL) as f:
                df = hipparcos.load_dataframe(f)
            self.obj = skyfield.Star.from_dataframe(df.loc[int(self.name)])

        elif self.type == self.TYPE_RA_DEC:
            self.obj = position_of_radec(ra_hours=self.ra / 360 * 24, dec_degrees=self.dec)

        else:
            assert False, f"Invalid target type: {self.type}"

        self._initialized = True

    def get_next_pass(self):
        """ Return next pass or None """
        return self.passes[0] if len(self.passes) else None

    def passes_contain(self, start_time, end_time=None, period=24):
        start_time = parse_time(start_time).utc_datetime()
        end_time = parse_time(end_time) if end_time is not None else start_time + timedelta(hours=period)
        return self.passes is not None and len(self.passes) > 0 and \
            self.passes_start_time <= start_time and self.passes_end_time >= end_time

    def calculate_passes(self, start_time: Union[None, str, datetime, skyfield.Time] = None,
                         end_time: Union[None, str, datetime, skyfield.Time] = None, period: float = 24,
                         min_elevation: float = 0, min_max_elevation: float = 0, sun_max_elevation: float = None,
                         sunlit: bool = None) -> list[Pass]:
        """
        Calculate passes for the satellite.

        Args:
            start_time:         start time for pass calculation, defaults to now
            period:             how many hours to calculate the passes for, defaults to 24 hours
            end_time:           if specified, overrides the period
            min_elevation:      minimum value for the maximum elevation for the pass to be considered valid
            min_max_elevation:  horizon to use for the calculation, defaults to 0
            sun_max_elevation:  maximum elevation of the sun for the pass to be considered valid
            sunlit:             if True, only calculate passes when the satellite is sunlit
        """

        assert self._initialized, "CelestialObject not initialized, call initialize() first"

        # start time for pass calculation
        t0 = parse_time(start_time)

        # end time for pass calculation
        t1 = parse_time(end_time) if end_time is not None else start_time + timedelta(hours=period)

        # calculate passes
        obj_gs = self.obj - (self.earth + self.gs)
        t_event, events = find_events(obj_gs, t0, t1, min_elevation, min_max_elevation,
                                      CelestialObject.BODIES, sun_max_elevation, sunlit)
        self.passes = events_to_passes(self.name, obj_gs, t_event, events, min_max_elevation)
        self.passes_start_time = t0.utc_datetime()
        self.passes_end_time = t1.utc_datetime()
        return self.passes

    def __str__(self):
        """ Return string to describing the satellite object"""
        type = {self.TYPE_STAR: "Star", self.TYPE_SSB: "SSB", self.TYPE_RA_DEC: "RA/DEC"}[self.type]
        return f"{self.name} ({type})" + ("" if self._initialized else " [non-initialized]")


class SkyfieldModuleMixin:
    """
    Provides a BaseModule derived module with
        - get_satellite() method that returns a Satellite object, maintaining a cache
        - get_celestial_object() method that returns a CelestialObject object, maintaining a cache
    """

    def __init__(self, *args, **kwargs):
        # calls the base module constructor
        super().__init__(*args, **kwargs)

        self.satellites: dict[str, Satellite] = {}
        self.celestional_objects: dict[str, CelestialObject] = {}

        # Open config file
        with open(cfg_path("groundstation.yaml")) as f:
            self.gs_config = yaml.load(f, Loader=yaml.Loader)['groundstation']

        # Create observer from config file
        self.gs = skyfield.Topos(
            latitude=skyfield.Angle(degrees=self.gs_config["latitude"]),
            longitude=skyfield.Angle(degrees=self.gs_config["longitude"]),
            elevation_m=self.gs_config["elevation"]
        )

    async def get_satellite(self, target: str,
                            start_time: Union[None, str, datetime, skyfield.Time] = None,
                            end_time: Union[None, str, datetime, skyfield.Time] = None,
                            min_elevation: float = 0,
                            min_max_elevation: float = 0,
                            sun_max_elevation: float = None,
                            sunlit: bool = None,
                            ) -> Optional[Satellite]:
        await asyncio.sleep(0)
        sat = self.satellites.get(target, None)
        pass_calc_kwargs = dict(start_time=start_time, end_time=end_time, min_elevation=min_elevation,
                                min_max_elevation=min_max_elevation, sun_max_elevation=sun_max_elevation,
                                sunlit=sunlit)

        # Ensure recent TLEs used
        if sat is None or sat.tle_age_days > 1:
            try:
                # TODO: remove the following work-around sleep, which is currently needed so that tle server
                #       has time to update the TLEs when starting porthouse
                await asyncio.sleep(5)
                self.log.debug("Requesting TLE for %s", target)
                ret = await self.send_rpc_request("tracking", "tle.rpc.get_tle", {"satellite": target})
            except RPCRequestError as e:
                self.log.error("Failed to request TLE: %s", e.args[0])
                return

            sat = Satellite(target, ret["tle1"], ret["tle2"], self.gs)

            self.log.debug(f"Calculating passes for {target}: {pass_calc_kwargs}")
            sat.calculate_passes(**pass_calc_kwargs)

            self.satellites[target] = sat

        # Ensure enough passes are available
        elif not sat.passes_contain(start_time, end_time):
            self.log.debug(f"Calculating passes for {target}")
            sat.calculate_passes(**pass_calc_kwargs)

        if sat.tle_age_days > 14:
            self.log.warning(f"TLE lines for \"{target}\" are {sat.tle_age_days:%.1f} days old and might be inaccurate!")
        if len(sat.passes) == 0:
            self.log.warning(f"No passes generated for \"{target}\"!")

        return sat

    async def get_celestial_object(self, target: str,
                                   start_time: Union[None, str, datetime, skyfield.Time] = None,
                                   end_time: Union[None, str, datetime, skyfield.Time] = None,
                                   min_elevation: float = 0,
                                   min_max_elevation: float = 0,
                                   sun_max_elevation: float = None,
                                   sunlit: bool = None,
                                   ) -> Optional[CelestialObject]:

        obj = self.celestional_objects.get(target, None)
        pass_calc_kwargs = dict(start_time=start_time, end_time=end_time, min_elevation=min_elevation,
                                min_max_elevation=min_max_elevation, sun_max_elevation=sun_max_elevation,
                                sunlit=sunlit)

        if obj is None:
            try:
                obj = CelestialObject(target, self.gs)
                with ThreadPoolExecutor() as executor:
                    await asyncio.get_running_loop().run_in_executor(executor, obj.initialize)
                with ThreadPoolExecutor() as executor:
                    await asyncio.get_running_loop().run_in_executor(executor,
                                                                     lambda: obj.calculate_passes(**pass_calc_kwargs))

                self.celestional_objects[target] = obj
            except Exception as e:
                self.log.error(f"Failed to initialize celestial object \"{target}\": {e}")
                return None

        elif not obj.passes_contain(start_time, end_time):
            with ThreadPoolExecutor() as executor:
                await asyncio.get_running_loop().run_in_executor(executor,
                                                                 lambda: obj.calculate_passes(**pass_calc_kwargs))

        else:
            await asyncio.sleep(0)

        if len(obj.passes) == 0:
            self.log.warning(f"No passes generated for \"{target}\"!")

        return obj


def parse_time(t: Union[None, str, datetime, skyfield.Time]) -> skyfield.Time:
    if t is None:
        dt = datetime.utcnow().replace(tzinfo=timezone.utc)
    elif isinstance(t, str):
        dt = datetime.fromisoformat(t.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
    elif isinstance(t, datetime):
        dt = t.replace(tzinfo=timezone.utc)
    elif isinstance(t, skyfield.Time):
        dt = t.utc_datetime()
    else:
        raise ValueError("Invalid time type")

    return ts.utc(dt)


def find_events(obj_gs: vectorlib.VectorFunction, t0: skyfield.Time, t1: skyfield.Time,
                min_elevation: float, min_max_elevation: float, ephem=None,
                max_sun_elevation: Optional[float] = None, sunlit=None) -> tuple[list, list]:
    """
    Find AOS/Max Elevation/LOS events for an object observed from at a groundstation.
    Copied from skyfield.sgp4lib.find_events and slightly modified because sgp4lib didn't support barycentric positions.
    Added optional conditions for sunlit=True/False and max_sun_elevation.
    """

    assert max_sun_elevation is None or ephem is not None and 'Sun' in ephem, \
        "Sun position required through the ephem param for max_sun_elevation"
    assert sunlit is None or hasattr(obj_gs, 'is_sunlit') and ephem is not None and 'Sun' in ephem and 'Earth' in ephem, \
        "Sun and Earth positions required through the ephem param for sunlit=True"

    def cheat(t):
        # still valid for our purposes?
        t.gast = t.tt * 0.0
        t.M = t.MT = np.identity(3)

    def elevation(t):
        cheat(t)
        return obj_gs.at(t).altaz()[0].degrees

    half_second = 0.5 / 24*60*60
    t_max, el_max = searchlib.find_maxima(t0, t1, elevation, half_second, 12)
    if not t_max:
        return t_max, np.ones_like(t_max)

    # Filter out passes with too low max elevation
    keepers = el_max >= min_max_elevation
    jdmax = t_max.tt[keepers]
    ones = np.ones_like(jdmax, 'uint8')

    # Finally, find the rising and setting that bracket each maximum
    # altitude.  We guess that the satellite will be back below the
    # horizon in between each pair of adjancent maxima.

    def unobservable_at(t):
        cheat(t)
        obj_above_horizon = obj_gs.at(t).altaz()[0].degrees > min_elevation

        sun_below_horizon = True
        if max_sun_elevation is not None:
            # check that its dark (addition by me)
            sun_below_horizon = obj_gs.at(t).observe(ephem['Sun']).apparent().altaz()[0].degrees < max_sun_elevation

        obj_sunlit = True
        if sunlit is not None:
            # check whether the object is sunlit (addition by me)
            # obj_sunlit = obj_gs.at(t).observe(ephem['Sun']).apparent()  # slower
            obj_sunlit = obj_gs.at(t).is_sunlit(ephem)
            if not sunlit:
                obj_sunlit = not obj_sunlit

        return not (obj_above_horizon and sun_below_horizon and obj_sunlit)

    # The `jdo` array are the times of maxima, with their averages
    # in between them.  The start and end times are thrown in too,
    # in case a rising or setting is lingering out between a maxima
    # and the ends of our range.  Could this perhaps still miss a
    # stubborn rising or setting near the ends?
    doublets = np.repeat(np.concatenate(((t0.tt,), jdmax, (t1.tt,))), 2)
    jdo = (doublets[:-1] + doublets[1:]) / 2.0

    # Use searchlib.find_discrete to find AOS/LOS events
    trs, rs = searchlib.find_discrete(t0.ts, jdo, unobservable_at, half_second, 8)

    jd = np.concatenate((jdmax, trs.tt))
    v = np.concatenate((ones, rs * 2))

    i = jd.argsort()
    return ts.tt_jd(jd[i]), v[i]


def events_to_passes(obj_name: str, obj_gs: object, t_event: list, events: list,
                     min_max_elevation: float) -> list[Pass]:
    passes = []
    t_aos, az_aos, t_max, el_max, az_max, t_los, az_los = None, None, None, None, None, None, None

    # Format the event list to a pass list
    for t, event in zip(t_event, events):
        el, az, _ = obj_gs.at(t).altaz()

        if event == 0:  # AOS
            t_aos, az_aos = t.utc_datetime(), az.degrees
        elif event == 1:  # Max
            t_max, el_max, az_max = t.utc_datetime(), el.degrees, az.degrees
        elif event == 2:  # LOS
            t_los, az_los = t.utc_datetime(), az.degrees

            # Make sure we have all details
            if t_aos and t_max and el_max > min_max_elevation:
                passes.append(
                    Pass(obj_name, "oh2ags", t_aos, az_aos, t_max, el_max, az_max, t_los, az_los, 1))

            t_aos, az_aos, t_max, el_max, t_los, az_los = None, None, None, None, None, None

    return passes

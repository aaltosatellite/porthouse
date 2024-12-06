
from enum import IntEnum
from datetime import datetime, timedelta, timezone
from typing import Union, Optional, Callable
import asyncio
from concurrent.futures import ThreadPoolExecutor
import yaml

import numpy as np

from skyfield import searchlib
from skyfield import vectorlib
from skyfield.data import hipparcos
from skyfield.positionlib import position_of_radec, Geometric, Apparent, Barycentric
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
            t_aos: datetime, az_aos: float, el_aos: float,
            t_max: datetime, az_max: float, el_max: float,
            t_los: datetime, az_los: float, el_los: float,
            orb_no: int = None, status: PassStatus = PassStatus.WAITING):
        """ Initialize pass """
        self.name = name
        self.gs = gs
        self.status = status

        self.t_aos = t_aos
        self.az_aos = az_aos
        self.el_aos = el_aos
        self.t_max = t_max
        self.az_max = az_max
        self.el_max = el_max
        self.t_los = t_los
        self.az_los = az_los
        self.el_los = el_los

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
            "el_aos": self.el_aos,
            "t_max": self.t_max.isoformat(),
            "az_max": self.az_max,
            "el_max": self.el_max,
            "t_los": self.t_los.isoformat(),
            "az_los": self.az_los,
            "el_los": self.el_los,
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


class GroundStation:
    def __init__(self):
        # Open config file
        with open(cfg_path("groundstation.yaml")) as f:
            self.config = yaml.load(f, Loader=yaml.Loader)['groundstation']

        # Create observer from config file
        self.pos = skyfield.Topos(
            latitude=skyfield.Angle(degrees=self.config["latitude"]),
            longitude=skyfield.Angle(degrees=self.config["longitude"]),
            elevation_m=self.config["elevation"]
        )

    def __str__(self):
        return f"GroundStation ({self.config['name']})"


class Satellite:
    """ Class to store satellite info """

    def __init__(self, name: str, tle1: str, tle2: str, gs: skyfield.Topos = None, earth=None):
        """ Initialize satellite object """
        self.name = name
        self.tle1 = tle1
        self.tle2 = tle2
        self.gs = gs
        self.earth = earth

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

    def pos_at(self, time: Union[None, str, datetime, skyfield.Time], accurate=False) -> Geometric:
        t = parse_time(time)
        if accurate and self.earth is not None:
            return (self.earth + self.gs).at(t).observe(self.earth + self.sc).apparent()
        else:
            return (self.sc - self.gs).at(t)

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
        end_time = parse_time(end_time).utc_datetime() if end_time is not None else start_time + timedelta(hours=period)
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

        if False and sunlit is None and sun_max_elevation is None:
            # Find all the events for the satellite, as before
            # TODO: could be removed as it's not used anymore (see False in if statement)
            t_event, events = self.sc.find_events(self.gs, start_time - timedelta(seconds=60),
                                                  end_time + timedelta(seconds=60), min_elevation)
        else:
            # Use own version of find_events that takes into account sunlit and sun_max_elevation params
            if CelestialObject.EARTH is None:
                CelestialObject.init_bodies()

            accurate = sunlit is not None or sun_max_elevation is not None
            margin_s = 12 * 60 * 60 if accurate else 0
            t_event, events = find_events(CelestialObject.EARTH + self.gs, CelestialObject.EARTH + self.sc,
                                          start_time - timedelta(seconds=60), end_time + timedelta(seconds=60),
                                          min_elevation, min_max_elevation, ephem=CelestialObject.BODIES,
                                          max_sun_elevation=sun_max_elevation, sunlit=sunlit, accurate=accurate,
                                          orbits_per_day=self.sc.model.no_kozai / np.pi / 2 * 60 * 24,
                                          margin_s=margin_s, partial_last_pass=False, debug=False)

        self.passes = events_to_passes(self.name, lambda t: (self.sc - self.gs).at(t).altaz(),
                                       t_event, events, min_max_elevation)
        self.passes_start_time = start_time.utc_datetime()
        self.passes_end_time = end_time.utc_datetime()
        if len(self.passes) == 0:
            print("No passes found, debug info: "
                  f"{t_event.utc_iso()} | {events} | {start_time - timedelta(seconds=60)} | {end_time + timedelta(seconds=60)} | "
                  f"{min_elevation} | {min_max_elevation} | {sun_max_elevation} | {sunlit}")

        # sanity check
        secs_per_half_orbit = 0.5 / (self.sc.model.no_kozai/np.pi/2/60)   # for inf high orbit
        for p in self.passes:
            if (p.t_los - p.t_aos).total_seconds() > secs_per_half_orbit:
                print(f"Pass too long, half orbit [s]: {secs_per_half_orbit}): {p}, debug info: "
                      f"{t_event.utc_iso()} | {events} | {start_time - timedelta(seconds=60)} | {end_time + timedelta(seconds=60)} | "
                      f"{min_elevation} | {min_max_elevation} | {sun_max_elevation} | {sunlit}")

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
        self.gs = gs or GroundStation().pos

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

    def pos_at(self, time: Union[None, str, datetime, skyfield.Time], accurate=True) -> Apparent:
        assert self._initialized, "CelestialObject not initialized"
        t = parse_time(time)
        gs = self.earth + self.gs
        return gs.at(t).observe(self.obj).apparent()

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
            # self.obj = position_of_radec(ra_hours=self.ra / 360 * 24, dec_degrees=self.dec,
            #                              center=0)  # solarsystem barycentric
            self.obj = skyfield.Star(ra_hours=self.ra / 360 * 24, dec_degrees=self.dec)

        else:
            assert False, f"Invalid target type: {self.type}"

        self._initialized = True

    def get_next_pass(self):
        """ Return next pass or None """
        return self.passes[0] if len(self.passes) else None

    def passes_contain(self, start_time, end_time=None, period=24):
        start_time = parse_time(start_time).utc_datetime()
        end_time = parse_time(end_time).utc_datetime() if end_time is not None else start_time + timedelta(hours=period)
        return self.passes is not None and len(self.passes) > 0 and \
            self.passes_start_time <= start_time and self.passes_end_time >= end_time

    def calculate_passes(self, start_time: Union[None, str, datetime, skyfield.Time] = None,
                         end_time: Union[None, str, datetime, skyfield.Time] = None, period: float = 24,
                         min_elevation: float = 0, min_max_elevation: float = 0, sun_max_elevation: float = None,
                         sunlit: bool = None, partial_last_pass=False) -> list[Pass]:
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
            partial_last_pass:  Default is False, if True, the last pass is allowed to be partial
        """

        assert self._initialized, "CelestialObject not initialized, call initialize() first"

        # start time for pass calculation
        t0 = parse_time(start_time)

        # end time for pass calculation
        t1 = parse_time(end_time) if end_time is not None else start_time + timedelta(hours=period)

        # calculate passes
        gs = self.earth + self.gs
        t_event, events = find_events(gs, self.obj, t0, t1, min_elevation, min_max_elevation,
                                      ephem=CelestialObject.BODIES, max_sun_elevation=sun_max_elevation, sunlit=sunlit,
                                      accurate=True, orbits_per_day=1.0, margin_s=12 * 60 * 60,
                                      partial_last_pass=partial_last_pass, debug=False)
        self.passes = events_to_passes(self.name, lambda t: gs.at(t).observe(self.obj).apparent().altaz(),
                                       t_event, events, min_max_elevation)
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
        self.gs = GroundStation()

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
                self.log.debug("Requesting TLE for %s", target)
                ret = await self.send_rpc_request("tracking", "tle.rpc.get_tle", {"satellite": target}, timeout=6)
            except RPCRequestError as e:
                self.log.error("Failed to request TLE: %s", e.args[0], exc_info=True)
                return

            sat = Satellite(target, ret["tle1"], ret["tle2"], self.gs.pos)

            self.log.debug(f"Calculating passes for {target}: {pass_calc_kwargs}")
            sat.calculate_passes(**pass_calc_kwargs)

            self.satellites[target] = sat

        # Ensure enough passes are available
        elif not sat.passes_contain(start_time, end_time):
            self.log.debug(f"Calculating passes for {target}")
            sat.calculate_passes(**pass_calc_kwargs)

        if sat.tle_age_days > 14:
            self.log.warning(f"TLE lines for \"{target}\" are {sat.tle_age_days:.1f} days old and might be inaccurate!")
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
                                   partial_last_pass: bool = False,
                                   ) -> Optional[CelestialObject]:

        obj = self.celestional_objects.get(target, None)
        pass_calc_kwargs = dict(start_time=start_time, end_time=end_time, min_elevation=min_elevation,
                                min_max_elevation=min_max_elevation, sun_max_elevation=sun_max_elevation,
                                sunlit=sunlit, partial_last_pass=partial_last_pass)

        if obj is None:
            try:
                obj = CelestialObject(target, self.gs.pos)
                with ThreadPoolExecutor() as executor:
                    await asyncio.get_running_loop().run_in_executor(executor, obj.initialize)

                self.log.debug(f"Calculating passes for {target}: {pass_calc_kwargs}")
                with ThreadPoolExecutor() as executor:
                    await asyncio.get_running_loop().run_in_executor(executor,
                                                                     lambda: obj.calculate_passes(**pass_calc_kwargs))

                self.celestional_objects[target] = obj
            except Exception as e:
                self.log.error(f"Failed to initialize celestial object \"{target}\": {e}", exc_info=True)
                return None

        elif not obj.passes_contain(start_time, end_time):
            self.log.debug(f"Calculating passes for {target}: {pass_calc_kwargs}")
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


def find_events(gs: vectorlib.VectorFunction, obj: vectorlib.VectorFunction, t0: skyfield.Time, t1: skyfield.Time,
                min_elevation: float, min_max_elevation: float, ephem=None,
                max_sun_elevation: Optional[float] = None, sunlit=None, accurate=True, margin_s=0,
                orbits_per_day=24/1.5, partial_last_pass=False, debug=False) -> tuple[list, list]:
    """
    Find AOS/Max Elevation/LOS events for an object observed from at a groundstation.
    Copied from skyfield.sgp4lib.find_events and slightly modified because sgp4lib didn't support barycentric positions.
    Added optional conditions for sunlit=True/False and max_sun_elevation.
    """

    assert type(t0) == skyfield.Time and type(t1) == skyfield.Time, "t0 and t1 must be of type skyfield.Time"
    assert max_sun_elevation is None or ephem is not None and 'Sun' in ephem, \
        "Sun position required through the ephem param for max_sun_elevation"
    assert sunlit is None or ephem is not None and 'Sun' in ephem and 'Earth' in ephem, \
        "Sun and Earth positions required through the ephem param for sunlit=True"

    if not accurate:
        # for close objects such as low Earth orbit satellites, ignores e.g. light travel time
        def cheat(t):
            # still valid for our purposes?
            t.gast = t.tt * 0.0
            t.M = t.MT = np.identity(3)

        def elevation(t):
            cheat(t)
            return (obj - gs).at(t).altaz()[0].degrees

    else:
        # for more distant objects such as planets and stars, takes light travel time
        # and relativistic effects into account
        def elevation(t):
            o = gs.at(t).observe(obj).apparent()
            return o.altaz('standard')[0].degrees   # takes into account atmospheric refraction

    def unobservable_at(t, ele=None):
        if not accurate:
            cheat(t)

        if ele is None:
            ele = elevation(t)

        tests = [ele > min_elevation]

        if max_sun_elevation is not None:
            # check that its dark (addition by me)
            sun_below_horizon = gs.at(t).observe(ephem['Sun']).apparent().altaz()[0].degrees < max_sun_elevation
            tests.append(sun_below_horizon)

        if sunlit is not None:
            # check whether the object is sunlit (addition by me)
            if not accurate:
                obj_sunlit = (obj - gs).at(t).is_sunlit(ephem)
            else:
                # NOTE: the following did not work, so we use the not so accurate method for now
                # obj_sunlit = obj.at(t).observe(ephem['Sun']).apparent().altaz()[0].degrees() > 0
                obj_sunlit = (obj - gs).at(t).is_sunlit(ephem)

            if not sunlit:
                obj_sunlit = np.logical_not(obj_sunlit)
            tests.append(obj_sunlit)

        return np.logical_not(np.logical_and.reduce(tests))

    def masked_elevation(t):
        ele = elevation(t)
        mask = unobservable_at(t, ele)
        if mask.ndim == 0:
            return 0.0 if mask else ele
        ele[mask] -= 180.0
        return ele

    masked_elevation.step_days = min(0.25, 0.05 / max(orbits_per_day, 1.0))  # determines initial step size

    if debug:
        eles = masked_elevation(ts.tt_jd(np.linspace(t0.tt, t1.tt, 100)))
        print(f"Elevations between {t0.tt} and {t1.tt} (step_days: {masked_elevation.step_days}): {eles}")

    day_in_secs = 24 * 60 * 60
    t_max, el_max = searchlib.find_maxima(t0, t1, masked_elevation, 0.5 / day_in_secs, 12)

    if margin_s > 0:
        t_max = ts.tt_jd([t0.tt] + list(t_max.tt) + [t1.tt])
        el_max = np.array([elevation(t_max[0])] + list(el_max) + [elevation(t_max[-1])])

    if debug:
        print(f"Maxima: {t_max.tt} | {el_max}")

    if not t_max:
        return t_max, np.ones_like(t_max)

    # Filter out passes with too low max elevation
    keepers = el_max >= min_max_elevation
    jdmax = t_max.tt[keepers]
    ones = np.ones_like(jdmax, 'uint8')

    # Finally, find the rising and setting that bracket each maximum
    # altitude.  We guess that the satellite will be back below the
    # horizon in between each pair of adjancent maxima.

    # The `jdo` array are the times of maxima, with their averages
    # in between them.  The start and end times are thrown in too,
    # in case a rising or setting is lingering out between a maxima
    # and the ends of our range.  Could this perhaps still miss a
    # stubborn rising or setting near the ends?
    doublets = np.repeat(np.concatenate(((t0.tt - margin_s/3600/24,), jdmax, (t1.tt + margin_s/3600/24,))), 2)
    jdo = (doublets[:-1] + doublets[1:]) / 2.0

    # Use searchlib._find_discrete to find rising and setting events
    trs, rs = searchlib._find_discrete(t0.ts, jdo, unobservable_at, 0.5 / day_in_secs, 8)

    jd = np.concatenate((jdmax, trs.tt))
    v = np.concatenate((ones, rs * 2))

    # Sort the events by time, then by value in case max elevation happens at the same time as observability changes
    i = np.array(list(zip(jd, v)), dtype=[('jd', 'f8'), ('v', 'f8')]).argsort(order=('jd', 'v'))
    jd, v = jd[i], v[i]

    if len(v) > 0 and v[0] == 1:
        # The first event is a maximum, so the satellite is already up, add a rising event at the start.
        #   - Partial pass at the beginning is ok as we want to get a currently visible pass included also.
        jd = np.concatenate(([t0.tt - 1/3600/24], jd))
        v = np.concatenate(([0], v))

    if partial_last_pass and len(v) > 0 and v[-1] == 1:
        # The last event is a maximum, so the satellite is still up, add a setting event at the end.
        #  - Best not used for scheduling, instead better to wait for later addition of that pass, otherwise
        #    will the pass will be split into two unnecessarily. For tracking its no problem though.
        jd = np.concatenate((jd, [t1.tt + 1/3600/24]))
        v = np.concatenate((v, [2]))

    if debug:
        print(f"Events (partial_last_pass={partial_last_pass}): {jd} | {v}")

    return ts.tt_jd(jd), v


def events_to_passes(obj_name: str, altaz_fn: Callable, t_event: list, events: list,
                     min_max_elevation: float) -> list[Pass]:
    passes = []
    t_aos, t_max, az_max, el_max, t_los = [None] * 5

    # Format the event list to a pass list
    for t, event in zip(t_event, events):
        if event == 0:  # AOS
            t_aos = t
        elif event == 1:  # Max
            # there can be extra max events between AOS and LOS due to start and end time limits,
            # we keep the highest one
            _t_max = t
            _el_max, _az_max, _ = altaz_fn(_t_max)
            if el_max is None or _el_max.degrees > el_max.degrees:
                t_max, az_max, el_max = _t_max, _az_max, _el_max
        elif event == 2:  # LOS
            t_los = t

            # Make sure we have all details
            if t_aos is not None and t_max is not None:
                if el_max.degrees > min_max_elevation:
                    el_aos, az_aos, _ = altaz_fn(t_aos)
                    el_los, az_los, _ = altaz_fn(t_los)
                    passes.append(Pass(obj_name, "oh2ags",
                                       t_aos.utc_datetime(), az_aos.degrees, el_aos.degrees,
                                       t_max.utc_datetime(), az_max.degrees, el_max.degrees,
                                       t_los.utc_datetime(), az_los.degrees, el_los.degrees))

            t_aos, t_max, az_max, el_max, t_los = [None] * 5
        else:
            assert False, "Invalid event: %s" % event

    return passes


def spherical2cartesian_deg(az, el, r=1.0):
    az, el = np.radians(az), np.radians(el)
    x = r * np.cos(el) * np.cos(az)
    y = r * np.cos(el) * np.sin(az)
    z = r * np.sin(el)
    return x, y, z


def angle_between_deg(v1, v2):
    try:
        v1 = np.array(v1)
        v2 = np.array(v2)
        assert len(v1) == len(v2) == 3 and v1.shape == v2.shape == (3,), "vectors must be 3D"
    except Exception:
        raise ValueError("vectors must be 3D, now: v1=%s, v2=%s" % (v1, v2))

    return np.degrees(np.arccos(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))))


def angle_between_el_az_deg(az1, el1, az2, el2):
    v1 = spherical2cartesian_deg(az1, el1)
    v2 = spherical2cartesian_deg(az2, el2)
    return angle_between_deg(v1, v2)


if __name__ == "__main__":
    target = "Suomi-100"
    gs = GroundStation()
    tle = {
        "Suomi-100": {
            "name": "Suomi-100",
            "tle1": "1 43804U 18099AY  24341.14375093  .00014948  00000-0  85933-3 0  9999\r",
            "tle2": "2 43804  97.5033  36.1570 0015289  73.3563 286.9345 15.12480927328618\r",
        },
    }[target]

    sat = Satellite(target, tle["tle1"], tle["tle2"], gs.pos)
    sat.calculate_passes(start_time="2024-12-06T10:00:00", end_time="2024-12-08T10:00:00",
                         min_elevation=0.0, min_max_elevation=0.0,
                         sun_max_elevation=None, sunlit=None)
    print(sat.passes)

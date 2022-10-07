
from __future__ import annotations
from enum import IntEnum
import datetime
import skyfield.api as skyfield

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
            sat_name: str,
            gs_name: str,
            t_aos: datetime, az_aos: float,
            t_max: datetime, el_max: float, az_max: float,
            t_los: datetime, az_los: float,
            orb_no: int = None):
        """ Initialize pass """
        self.name = sat_name
        self.gs = gs_name
        self.status = PassStatus.WAITING

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
        return f"Pass {self.name} for {sat.gs} " \
               f"(AOS: {self.aos.isoformat()}, LOS: {self.los.isoformat()})"


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

    def is_(self):
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

    def is_inside(self, other: Pass):
        """ Checks if self is inside other pass. """
        return not self.is_outside(other)

    def is_outside(self, other: Pass):
        """ Checks if self is outside other pass. """
        return (self.t_aos <= other.los) and (self.t_los >= other.aos)

    def is_reaching_into(self, other: Pass):
        """ Checks if self begins before and ends inside other pass. """
        # AOS overlap
        return self.t_aos < other.aos < self.t_los

    def is_reaching_out(self, other: Pass):
        """ Checks if self begins inside and ends after other pass. """
        # LOS overlap
        return self.t_aos < other.los < self.t_los


class Satellite:
    """ Class to store satellite info """

    def __init__(self, name: str, tle1: str, tle2: str):
        """ Initialize satellite object """
        self.name = name
        self.tle1 = tle1
        self.tle2 = tle2
        self.azel = (0, 0, 0)
        self.gs = None

        self.sc = skyfield.EarthSatellite(self.tle1, self.tle2)
        self.passes = []

    def __str__(self):
        """ Return string to describing the satellite object"""
        return f"Satellite({self.name}"

    def get_next_pass(self):
        """ Return next pass or None """
        return self.passes[0] if len(self.passes) else None

    def to_dict(self, tle: bool=False):
        """
        """

        now = ts.now()

        sc = {
            "name": self.name,
        }

        if True and self.gs:
            #
            pos = (self.sc - self.gs).at(ts.from_datetime(now))
            el, az, range, _, _, range_rate = pos.frame_latlon_and_rates(skyfield.framelib.ecliptic_J2000_frame)

            sc.extend({
                "elevation": el.degrees,
                "azitmuth": az.degrees,
                "range": range.km,
                "range_rate": range_rate.m_per_s
            })

        if True:
            #
            geocentric = self.sc.at(now)
            lat, lon = wgs84.latlon_of(geocentric)
            alt = wgs84.height_of(geocentric)

            sc.extend({
                "latitude":  lat.degrees,
                "longitude": lon.degrees,
                "altitude": alt.km,
            })

        if True:
            sc["next_pass"] = self.passes[0].to_dict() if len(self.passes) else None

        if True:
            sc["passes"] = [ p.to_dict for p in self.passes ]

        if tle:
            sc["tle1"] = self.tle1
            sc["tle2"] = self.tle2

        return


    def calculate_passes(self,
            gs: skyfield.Topos,
            start_time: Union[None, datetime.datetime, skyfield.Time]=None,
            period: float = None,
            min_elevation: float=0
        ) -> None:
        """

        Args:
            gs:
            start_time:
            min_elevation:
        """

        self.passes = []

        # Determine the start time of the
        if start_time is None:
            t = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
        elif isinstance(start_time, datetime.datetime):
            t = start_time.replace(tzinfo=utc)
        elif isinstance(start_time, skyfield.Time):
            t = start_time.utc_datetime()
        else:
            raise ValueError("Invalid start_time type")

        if period is None:
            end_time = t + datetime.timedelta(hours=24)
        else:
            raise ValueError("Invalid period type")

        # Check if the satellite is already at the sky
        el, _, _ = (self.sc - gs).at(ts.utc(t)).altaz()
        if el.degrees > 0:
            t -= datetime.timedelta(minutes=30)

        # Find all the events for the satellite
        t_event, events = self.sc.find_events(gs, ts.utc(t), ts.utc(end_time), min_elevation)
        t_aos, az_aos, t_max, el_max, az_max, t_los, az_los = None, None, None, None, None, None, None

        #print("Calculating passes for %s (%s)" % (self.name, t.isoformat()))

        # Format the event list to a pass list
        pass_list = []
        for t, event in zip(t_event, events):
            el, az, _ = (self.sc - gs).at(t).altaz()

            if event == 0: # AOS
                t_aos, az_aos = t.utc_datetime(), az.degrees
            elif event == 1: # Max
                t_max, el_max, az_max = t.utc_datetime(), el.degrees, az.degrees
            elif event == 2: # LOS
                t_los, az_los = t.utc_datetime(), az.degrees

                # Make sure we have all details
                if t_aos and t_max:
                    #self.passes.append( Pass(t_aos, az_aos, t_max, el_max, t_los, az_los) )
                    self.passes.append( Pass(self.name, "oh2ags", t_aos, az_aos, t_max, el_max, az_max, t_los, az_los, 1))

                #print(" - Pass: AOS(%s, azimuth %.2f) Max(%s, elevation %.2f) LOS(%s, azimuth %.2f)" %
                #    (t_aos.isoformat(), az_aos, t_max.isoformat(), el_max, t_los.isoformat(), az_los))

                t_aos, az_aos, t_max, el_max, t_los, az_los = None, None, None, None, None, None

        return pass_list


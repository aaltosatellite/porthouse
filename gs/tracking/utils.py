
from __future__ import annotations
from enum import Enum
from datetime import datetime
import skyfield.api as skyfield


class PassStatus(Enum):
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
            aos: datetime,
            los: datetime,
            orb_no: int = None):
        """ Initialize pass """
        self.name = sat_name
        self.gs = gs_name
        self.status = status
        self.aos, self.los = aos, los
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
            "aos": self.aos.isoformat(),
            "los": self.los.isoformat(),
            "elevation": 0.0
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
            aos=datetime.fromisoformat(entry["aos"]),
            los=datetime.fromisoformat(entry["los"]),
            orb_no=entry.get("orb_no", None)
        )


    def is_future(self):
        return datetime.utcnow() < self.aos

    def is_(self):
        return self.aos < datetime.utcnow() < self.los

    def has_passed(self):
        return datetime.utcnow() > self.los


    def is_valid(self):
        """ Checks if the pass los is after aos. """
        return self.los > self.aos

    def __gt__(self, other):
        return self.aos > self.aos

    def __lt__(self, other):
        return self.aos < self.aos

    def is_inside(self, other: Pass):
        """ Checks if self is inside other pass. """
        return not self.is_outside(other)

    def is_outside(self, other: Pass):
        """ Checks if self is outside other pass. """
        return (self.aos <= other.los) and (self.los >= other.aos)

    def is_reaching_into(self, other: Pass):
        """ Checks if self begins before and ends inside other pass. """
        # AOS overlap
        return self.aos < other.aos < self.los

    def is_reaching_out(self, other: Pass):
        """ Checks if self begins inside and ends after other pass. """
        # LOS overlap
        return self.aos < other.los < self.los


class Satellite:
    """ Class to store satellite info """

    def __init__(self, name: str, tle1: str, tle2: str):
        """ Initialize satellite object """
        self.name = name
        self.tle1 = tle1
        self.tle2 = tle2

        self.sc = skyfield.EarthSatellite(self.tle1, self.tle2)
        self.passes = []

    def __str__(self):
        """ Return string to describing the satellite object"""
        return f"Satellite({self.name}"

    def get_next_pass(self):
        """ Return next pass or None """
        if len(self.passes) == 0:
            return None
        return self.passes[0]

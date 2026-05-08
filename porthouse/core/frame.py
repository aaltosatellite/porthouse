"""
    This module holds the general implemenation for a Frame class which is used
    to
"""

from datetime import datetime
from typing import Any, Dict, Optional

class FrameParsingError(Exception):
    """
    Blaa
    """

class Frame:
    """
    General
    """

    satellite: str
    source: Optional[str]
    timestamp: Optional[datetime]
    metadata: Dict[str, Any]
    data: bytes

    def __init__(self,
            satellite: str,
            source: str,
            timestamp: datetime,
            metadata: Dict[str, Any],
            data: bytes):
        """
        Construct a new frame object from individual arguments.

        Args:
            satellite: Satellite identifier/name
            source: Frame source identifier/name
            timestamp: Time of creation or reception
            data: Data contained in the frame as bytes
            metadata: Additional metadata as dictionary
        """
        self.satellite = satellite
        self.source = source
        self.timestamp = timestamp
        self.data = data
        self.metadata = metadata


    @classmethod
    def from_dict(cls, frm: Dict[str, Any]):
        """
        Parse frame from a dictionary object
        """

        timestamp = frm.get("timestamp", None)
        if timestamp:
            if timestamp.endswith("Z"):
                 timestamp = timestamp[:-1] + "+00:00"      #zulu-format is not supported in versions < Python 3.11
            timestamp = datetime.fromisoformat(timestamp)

        return cls(
            satellite=frm.get("satellite", None),
            source=frm.get("source", None),
            timestamp=timestamp,
            data=bytes.fromhex(frm.get("data", "")),
            metadata=frm.get("metadata", dict())
        )


    def to_dict(self):
        """
        Return frame as a dictionary object.
        """
        return {
            "satellite": self.satellite,
            "source": self.source,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "data": self.data.hex(),
            "metadata": self.metadata
        }

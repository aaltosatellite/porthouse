"""
    Utility functions for OpenMCT backend
"""
from datetime import datetime
from pytz import UTC

class WebRPCError(Exception):
    """ Exception to deliver a nice verbose error message to OpenMCT frontend """
    pass


def iso_timestamp_to_millis(timestamp: str) -> float:
    """
    Convert timestamp in ISO format to milliseconds since Unix epoch
    """
    return datetime_to_millis(datetime.fromisoformat(timestamp))

def datetime_to_millis(timestamp: datetime) -> int:
    """
    Convert datetime object in UTC to milliseconds since Unix epoch
    """
    timestamp = timestamp.replace(tzinfo=UTC).astimezone(tz=None)
    return int(timestamp.timestamp() * 1000)

def millis_to_datetime(millis: int) -> datetime:
    """
    Convert millisecond timestamp to datetime object
    """
    return datetime.utcfromtimestamp(millis / 1000.)

import struct
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

try:
    from .suo import SuoFrame
except ImportError:
    pass

def to_suo(pkt: Dict) -> Tuple[bytes, bytes, bytes]:
    """
    Convert

    Returns:
        Returns a tuple containing the three parts of the ZMQ message.

    Remarks:
        Must be used with ZMQ endpoint with multipart enabled.
    """
    frame = SuoFrame()
    frame.data = pkt["data"]

    return frame.to_bytes()


def from_suo(args) -> Dict[str, Any]:
    """
    Convert packet from SUO modem to JSON.

    Args:

    Returns:

    Remarks:
        Must be used with ZMQ endpoint with multipart enabled.
    """

    if len(args) != 3 or not isinstance(args[0], bytes) or not isinstance(args[1], bytes) or not isinstance(args[1], bytes):
        pass # OK

    frame = SuoFrame.from_bytes(*args)

    return {
        # "type": "uplink" if id == 1 else "downlink",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": frame.data.hex(),
        "metadata": frame.metadata
    }

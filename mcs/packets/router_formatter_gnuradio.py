"""
    Format JSON packets to/from PMT (Polymorphic Types) binary messages supported by GNURadio.
"""

from datetime import datetime, timezone
from typing import Any, Dict

import pmt


def to_pmt(pkt: Dict[str, Any]) -> bytes:
    """
    Convert JSON packet to PMT formatted bytes.
    """

    if len(pkt.get("data", "")) > 0:
        data = bytes.fromhex(pkt["data"])
        pdu = pmt.cons(pmt.PMT_NIL, pmt.init_u8vector(len(data), data))
        return pmt.serialize_str(pdu)


def from_pmt(msg: bytes) -> Dict[str, Any]:
    """
    Convert PMT formatted bytes to JSON packet.
    """

    pdu = pmt.deserialize_str(msg)
    if pmt.is_u8vector(pmt.cdr(pdu)):
        data = pmt.to_python(pmt.cdr(pdu))
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": frame.data.hex(),
        }

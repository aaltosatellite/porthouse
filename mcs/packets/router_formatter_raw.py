from datetime import datetime, timezone
from typing import Any, Dict


def raw_to_json(pkt: bytes) -> Dict[str, Any]:
    """
    Convert RAW packet to JSON struct
    """
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": pkt.hex(),
    }

def json_to_raw(pkt: Dict[str, Any]) -> bytes:
    """
    Convert JSON to RAW packet without any additional info
    """
    return bytes.fromhex(pkt["data"])

import struct
from datetime import datetime, timezone
from typing import Any, Dict, Tuple


# Skylink VC command codes
VC_CTRL_TRANSMIT_VC0      = 0
VC_CTRL_TRANSMIT_VC1      = 1
VC_CTRL_TRANSMIT_VC2      = 2
VC_CTRL_TRANSMIT_VC3      = 3

VC_CTRL_RECEIVE_VC0       = 4
VC_CTRL_RECEIVE_VC1       = 5
VC_CTRL_RECEIVE_VC2       = 6
VC_CTRL_RECEIVE_VC3       = 7

VC_CTRL_GET_STATE         = 10
VC_CTRL_STATE_RSP         = 11
VC_CTRL_FLUSH_BUFFERS     = 12

VC_CTRL_GET_STATS         = 13
VC_CTRL_STATS_RSP         = 14
VC_CTRL_CLEAR_STATS       = 15

VC_CTRL_SET_CONFIG        = 16
VC_CTRL_GET_CONFIG        = 17
VC_CTRL_CONFIG_RSP        = 18

VC_CTRL_ARQ_CONNECT       = 20
VC_CTRL_ARQ_DISCONNECT    = 21
VC_CTRL_ARQ_TIMEOUT       = 22

VC_CTRL_RESET_MAC         = 30


def to_skylink(pkt: Dict) -> bytes:
    """
    Create a data or control frame for Skylink VC interface.
    """

    # If the data is provided just send forward it.
    if len(pkt.get("data", "")) > 0:
        vc: int = pkt.get("vc", 0)
        return struct.pack("B", VC_CTRL_TRANSMIT_VC0 + vc) + bytes.fromhex(pkt["data"])

    # If metadata is defined and it has 'cmd' field, craft a control frame
    metadata = pkt.get("metadata", None)
    if metadata and "cmd" in metadata:
        cmd: str = metadata["cmd"]
        vc: int = metadata.get("vc", 0)

        if cmd == "get_state":
            return struct.pack("B", VC_CTRL_GET_STATE)
        elif cmd == "flush":
            return struct.pack("B", VC_CTRL_FLUSH_BUFFERS)
        elif cmd == "get_stats":
            return struct.pack("B", VC_CTRL_GET_STATS)
        elif cmd == "clear_stats":
            return struct.pack("B", VC_CTRL_CLEAR_STATS)
        elif cmd == "set_config":
            s = metadata["config"].encode() + b"\x00" + str(metadata["value"]).encode()
            return struct.pack("@B", VC_CTRL_SET_CONFIG) + s
        elif cmd == "get_config":
            return struct.pack("@B", VC_CTRL_GET_CONFIG) + metadata["config"].encode()
        elif cmd == "arq_connect":
            return struct.pack("BB", VC_CTRL_ARQ_CONNECT, vc)
        elif cmd == "arq_disconnect":
            return struct.pack("BB", VC_CTRL_ARQ_DISCONNECT, vc)
        elif cmd == "reset_mac":
            return struct.pack("B", VC_CTRL_RESET_MAC)
        else:
            raise RuntimeError(f"Unkown control command {cmd!r}")

    raise RuntimeError(f"Cannot translate frame {pkt} for Skylink")



def from_skylink(raw: bytes) -> Dict[str, Any]:
    """
    Convert packet from Skylink VC data or control frame to JSON.

    Args:
        raw: Raw bytes received from ZMQ socket.
    """

    cmd, data = raw[0], raw[1:]

    if VC_CTRL_RECEIVE_VC0 <= cmd <= VC_CTRL_RECEIVE_VC3:
        vc = cmd - VC_CTRL_RECEIVE_VC0

        return {
            "type": "downlink",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "vc": vc,
            "data": data.hex(),
            "metadata": { }
        }

    else:

        if cmd == VC_CTRL_STATE_RSP:
            #
            # Parse buffer states
            #

            vcs = []
            for i in range(4):
                state = struct.unpack("4H", data[8*i: 8*i + 8])
                vcs.append({
                    "arq_state": state[0],
                    "buffer_free": state[1],
                    "tx_frames": state[2],
                    "rx_frames": state[3],
                })

            metadata = {
                "rsp": "state",
                "state": vcs
            }

        elif cmd == VC_CTRL_STATS_RSP:
            #
            # Parse protocol statistics
            #

            stats = struct.unpack("8H", data)
            metadata = {
                "rsp": "stats",
                "stats": {
                    "rx_frames": stats[0],
                    "rx_fec_ok": stats[1],
                    "rx_fec_fail": stats[2],
                    "rx_fec_octs": stats[3],
                    "rx_fec_errs": stats[4],
                    "rx_arq_resets": stats[5],
                    "tx_frames": stats[6],
                    "tx_bytes": stats[7],
                }
            }

        elif cmd == VC_CTRL_CONFIG_RSP:
            #
            # Parse configuration
            #

            cfg, val = struct.unpack("II", data)
            metadata = {
                "rsp": "config",
                "cfg": cfg,
                "val": val,
            }

        elif cmd == VC_CTRL_ARQ_TIMEOUT:
            #
            # Parse ARQ timeout
            #
            metadata = {
                "rsp": "arq_timeout",
                "vc": struct.unpack("B", data)[0]
            }

        elif cmd == VC_CTRL_GET_CONFIG:
            #
            # Parse get config response
            #
            metadata = {
                "rsp": "config",
                "val": data.decode()
            }

        else:
            raise RuntimeError(f"Unknown control response {cmd!r}")

        return {
            "type": "control",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": None,
            "metadata": metadata
        }

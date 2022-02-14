"""
    SatNOGS telemetry importer script for FORESAIL-1


    The script loads its global settings from
    ```
    sat_id: XXXX-0123-4567-8901-2345
    #norad_cat_id: 99999

    # Production
    api_url: https://db.satnogs.org/api/
    api_key: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

    # Development
    #api_url: https://db-dev.satnogs.org/api/
    #api_key: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    ```

"""

import json
import requests
import traceback
from datetime import datetime

import zmq

import yaml
from porthouse.core.config import cfg_path
from porthouse.core.frame import Frame

import skylink
from foresail1.pus import Telemetry


"""
Connect to packet router JSON input endpoint
"""
zmq_ctx = zmq.Context()
sock = zmq_ctx.socket(zmq.PUB)
sock.connect("tcp://128.0.0.1:57000")


def submit_frame(timestamp: datetime, telemetry: bytes, metadata: dict) -> None:
    """
    Submit frame to Packet Router
    """
    frame = {
        "timestamp": timestamp.toisoformat(),
        "data": telemetry.tohex(),
        "source": "satnogs",
        "metadata": metadata
    }
    sock.send(json.dumps(frame))





satnogs_cfg = yaml.load(open(cfg_path("satnogs.yaml")), yaml.Loader)


if 1:
    """
    Get all frames from SatNOGS db
    """

    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(hours=24)

    args = {
        "sat_id": satnogs_cfg["sat_id"],
        #"norad_cat_id":
        #"transmitter":
        "start": start_time.isoformat() + "Z",
        "end": end_time.isoformat() + "Z",
    }

    headers = {
        "Authorization": "Token " + satnogs_cfg["api_key"]
    }

    r = requests.get(satnogs_cfg["api_url"] + "telemetry", params=args, headers=headers)

    if r.status_code != 200:
        raise RuntimeError(f"HTTP error {r.status_code}: {r.text}")


    for frame in r.json():


        try:
            timestamp = datetime.fromisoformat(frame["timestamp"].replace('Z', '+00:00'))
            raw_frame = bytes.fromhex(frame["frame"])

            frame = skylink.parse(raw_frame)

            # Has the frame some content? Not just control frame
            if len(frame.payload) > 0 and (frame.vc == 0 or frame.vc == 1):

                # Validate two first bytes in the header (confirm correct frame type and APID)
                if frame.payload[0:2] == b"\x00\x00":
                    continue

                metadata = {
                    "frame": frame["observer"],
                    "station_id": frame["station_id"],
                    "observation_id": frame["observation_id"],
                }

                submit_frame(timestamp, frame.payload, metadata)

        except Exception as ex:
            print("Failed to parse frame:", frame)
            traceback.print_exception(type(ex), ex, ex.__traceback__)
            print()

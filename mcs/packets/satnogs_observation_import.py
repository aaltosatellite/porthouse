#!/usr/bin/env python3
"""
    Satnogs database importer
"""

import sys
import requests
import re, json
import datetime
import time


"""
    Connect to packet router JSON input endpoint
"""
import zmq
zmq_ctx = zmq.Context()
sock = zmq_ctx.socket(zmq.PUB)
sock.connect("tcp://128.0.0.1:57000")


def slack_announce_observation(obs, total_frames, total_bytes):
    """
        Announce
    """

    txt  = f"**New SatNOGS observation ([#{obs['id']}](https://network.satnogs.org/observations/{obs['id']}/)) for {obs['norad_cat_id']}**\n"
    txt += f"Station: [{obs['station_name']}](https://network.satnogs.org/stations/{obs['ground_station']}/), "
    txt += f"AOS: {obs['start']}, LOS: {obs['end']}, Elevation: {obs['max_altitude']}\n"
    txt += f"Pushing {total_frames} decoded frames ({total_bytes} bytes) to Foresail-1 MCS."

    channel.basic_publish(msg.dumps({
        "msg": txt
    }), exchange="slack", routing_key="announce.foresail1p")


def broadcast_frame(timestamp, data, obs_id):
    """
        Send the JSON formated frame

        str = bytes().hex()
        bytes.fromhex(str)
    """

    frame = {
        "timestamp": timestamp.isoformat(),
        "data": data.hex(),
        "source": "satnogs",
        "metadata": {
            "obs": obs_id
        }
    }

    sock.send(json.dumps(frame))


def parse_timestamp(t):
    return datetime.datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


def iterate_observations(norad_id, end_time, start_time):
    """
        Generator to iterate observations from the SatNOGS database
    """

    if end_time < start_time:
        start_time, end_time = end_time, start_time

    args = {
        "start": start_time.isoformat(),
        "end": end_time.isoformat(),
        "satellite__norad_cat_id": norad_id,
        #"transmitter_uuid": "MVCWWqc9Xt4JfF36marnJfZ",
        "vetted_status": "good",
        "format": "json"
    }

    s = requests.Session()
    url_time_parser = re.compile("\d\d\d\d-\d\d-\d\dT\d\d-\d\d-\d\d")

    for page in range(1, 10):
        args["page"] = page

        # Get list of observations
        r = s.get("https://network.satnogs.org/api/data/", params=args)
        if r.status_code == 404: # API responses 404 when no page
            return
        if r.status_code != 200:
            raise RuntimeError(f"HTTP error {r.status_code}: {r.text}")

        # Foreach observation
        for obs in r.json():

            # Download demodulated frames
            for demod in obs["demoddata"]:

                # Parse time from the URL
                t = url_time_parser.search(demod["payload_demod"]).group(0)
                demod["timestamp"] = datetime.datetime.strptime(t, "%Y-%m-%dT%H-%M-%S").replace(tzinfo=datetime.timezone.utc)

                # Download the raw data
                demod["data"] = s.get(demod["payload_demod"]).content

            yield obs




OBS_LOG_FILE = ".satnogs-observation-log"

def check_for_new_observation(clean=False):
    """
        Check for new obseravation
    """

    obs_log = json.load(open(OBS_LOG_FILE, "r"))

    norad_id = 44878 # OPS-SAT
    end_time = datetime.datetime.utcnow()
    start_time = end_time - datetime.timedelta(hours=24)

    for obs in iterate_observations(norad_id, end_time, start_time):

        print()

        # Check if the observation is already in the log
        if str(obs["id"]) in obs_log.keys():
            print(f"#{obs['id']} already processed")
            continue

        print(f"New Observation: #{obs['id']} AOS: {obs['start']}, LOS: {obs['end']}, Status: {obs['vetted_status']}")

        if len(obs["demoddata"]) == 0:
            print("  No data...")
            continue

        total_packets, total_bytes = 0, 0
        for pkt in obs["demoddata"]:
            #print(f"{pkt['timestamp']}: {pkt['data']}")

            # Validate frame before publishing it
            if 0: # TODO
                print("Invalid telemetry frame!")

            #broadcast_frame(pkt["timestamp"], pkt["data"], obs["id"])

            total_packets += 1
            total_bytes += len(pkt['data'])


        print(f"Imported {total_packets} frames, {total_bytes}")
        print()

        #slack_announce_observation(obs, total_packets, total_bytes)

        # Mark the observation
        obs_log[obs["id"]] = obs["start"]

        # Save the modified log file
        with open(OBS_LOG_FILE, "w") as f:
            json.dump(obs_log, f)


    # Clean really old observations away from the log file
    if clean:
        now = datetime.datetime.utcnow()
        for obs_id in obs_log:
            delta = now - parse_timestamp(obs_log[obs_id])
            if delta.days > 14:
                del obs_log[obs_id]

    # Save the modified log file
    with open(OBS_LOG_FILE, "w") as f:
        json.dump(obs_log, f)



if __name__ == "__main__":

    if len(sys.argv) > 1:
        while True:
            check_for_new_observation()
            print("Sleeping for 1h...\n\n\n")
            time.sleep(3600) # Sleep one hour
    else:
        check_for_new_observation()

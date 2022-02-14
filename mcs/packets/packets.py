#!/usr/bin/env python3
"""
    Command line tool for accessing the packet database
"""

import os
import amqp
import json
import argparse
import datetime
from typing import List

from .database_api import PacketsDatabase
from porthouse.core.rpc import amqp_connect, send_rpc_request
from porthouse.core.config import load_globals




parser = argparse.ArgumentParser(description='Packets database')

# General configs
parser.add_argument('--amqp', dest="amqp_url",
    help="AMQP connection URL.")
parser.add_argument('--db', dest="db_url",
    help="PostgreSQL database URL.")

# Filters
parser.add_argument('--satellite',
    help="Filter results by the satellite identifier/name")
parser.add_argument('--type', dest="packet_type",
    help="Filter results by packet type")
parser.add_argument('--source',
    help="Filter results by packet source")
parser.add_argument('--after',
    help="Filter results by timestamp")
parser.add_argument('--before',
    help="Filter results by timestamp")

# Actions
parser.add_argument('--create_tables', action="store_true",
    help="If given a default packets table will be created to given the database.")
parser.add_argument('--totals', action="store_true",
    help="Get total number of bytes stored in the database")
parser.add_argument('--export', action="store_true")
parser.add_argument('--cron', action="store_true")

parser.add_argument('--routes', action="store_true",
    help="List all PacketRouter's endpoints and routes")
parser.add_argument('--route', nargs=2,
    help="Create a new route")
parser.add_argument('--unroute', nargs='*',
    help="Destroy route")

args = parser.parse_args()



def create_constrain_string() -> str:
    """
        Create contstraints string for the SQL query from given commandline arguments.
    """
    constraints: List[str] = []
    if args.satellite:
        constraints = f"satellite == {args.satellite!r}"
    if args.packet_type:
        constraints = f"type == {args.packet_type!r}"
    if args.source:
        constraints = f"source == {args.source!r}"
    if args.after:
        constraints = f"timestamp >= {args.after!r}"
    if args.before:
        constraints = f"satellite == {args.before!r}"

    return ("WERE " + " AND ".join("constraints") + " ") if constraints else ""


"""
    Connect SQL database and AMQP broker
"""
db = PacketsDatabase(args.db_url or load_globals().get("db_url", None), args.create_tables)
connection, channel = amqp_connect(args.amqp_url)


if args.create_tables:
    """
        Create packet table
    """
    pass # Nothing to do here. Tables were created during the database initialization.
    print("Done")

elif args.routes:
    """
    List all endpoints and routes
    """

    res = send_rpc_request("packets", "router.rpc.list")

    print()
    print("# ENDPOINTS:")
    print("Name:           | Type:           | Metadata:")
    print("----------------|-----------------|-----------------")
    for endpoint in res["endpoints"]:
        print(f"{endpoint['name']:<16}| {endpoint['type']:<16}|")
    print()

    print("# ROUTES:")
    print("Source          | Destination")
    print("----------------|-----------------")
    for route in res["routes"]:
        print(f"{route['source']:<16}| {route['destination']:<16}")
    print()


elif args.route:
    """
    Route selected
    """
    a, b = args.route
    print(f"Creating route {a!r} --> {b!r}")
    res = send_rpc_request("packets", "router.rpc.connect", a=a, b=b)

    if "error" in res:
        print("Failed to connect routes!", res["error"])

elif args.unroute:
    """
    Unroute selected
    """
    print(f"Unrouting {args.unroute[0]!r}")
    res = send_rpc_request("packets", "router.rpc.disconnect", a=args.unroute[0])

    if "error" in res:
        print("Failed to disconnect routes!", res["error"])

elif args.totals:
    """
        Print total number of frames and transferred bytes
    """

    smt = "SELECT source, satellite, type, COUNT(*), SUM(length(data)) FROM packets "
    smt += create_constrain_string()
    smt += "GROUP BY source, satellite, type"
    r = db.cursor.execute(smt)


    print()
    print("Source:          | Satellite:       | Type:            | Frames:          | Total bytes:")
    print("-----------------|------------------|------------------|------------------|------------------")
    for source, satellite, packet_type, frames, total in db.cursor.fetchall():

        if total >= 1048576: # Mega
            total = "%.1fM" % (total / 1048576)
        elif total >= 1024: # kilo
            total = "%.1fk" % (total / 1024)

        print(f"{source:<16} | {satellite:<16} | {packet_type:<16} | {frames:<16} | {total}")
    print()


elif args.export:
    """
        Dump raw frames to stdout
    """

    smt = "SELECT id, satellite, type, data FROM packets "
    smt += create_constrain_string()
    smt += "GROUP BY source, satellite, type"
    r = db.cursor.execute(smt)

    for id, satellite, packet_type, data in db.cursor.fetchall():
        print(f"#{id} {satellite} {type} {data}")


elif args.cron:
    """
        Generate filetransfer housekeeping frame from packets collected yesterday
    """

    # Calculate timespan
    yesterday = datetime.date.today() - datetime.timedelta(1)
    start = datetime.datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0) # TODO: UTC
    end = datetime.datetime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59)

    print("Timespan: ", start, end)

    r = db.cursor.execute(f"""
    SELECT type, source, data,
    FROM packets
    WHERE satellite='fs1' AND timestamp >= {start.isoformat(' ')} AND timestamp <= {end.isoformat(' ')}
    ORDER BY timestamp DESC;
    """)


    uplink = 0
    downlink = 0
    satnogs = 0

    for frame in db.cursor.fetchall():
        if frame[1] == "satnogs":
            satnogs += len(frame[2])
        elif frame[0] == "uplink":
            uplink += len(frame[2])
        elif frame[0] == "downlink":
            downlink += len(frame[2])

    print(f"Uplinked   {uplink} bytes")
    print(f"Downlinked {downlink} bytes")
    print(f"SatNogs    {satnogs} bytes")

    msg_dict = {
        "subsystem": "fs1.data",
        "timestamp": int(end.strftime("%s")),
        "source": __file__,
        "housekeeping": {
            "uplink": uplink,
            "downlink": downlink,

        },
        "metadata": {
            "start": start.isoformat(),
            "end": end.isoformat()
        }
    }

    msg = amqp.basic_message.Message(body=json.dumps(msg_dict))
    channel.basic_publish(msg, exchange='housekeeping', routing_key='fs1.store')

else:
    parser.print_help()

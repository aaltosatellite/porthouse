#!/usr/bin/env python3
"""
    This is tool to replay selected telemetry back to the telemetry prosessing system.
"""

import amqp
import json
import argparse
import sys, os, time
from database_api import PacketsDatabase


parser = argparse.ArgumentParser(description='Telemetry replayer')

# General configs
parser.add_argument('--amqp', dest="amqp_url",
    help="AMQP connection URL. If not given environment variable MCC_AMQP_ACCESS is used.")
parser.add_argument('--db', dest="db_url",
    help="PostgreSQL database URL. If not given environment variable MCC_DB_ACCESS is used.")

# Filters
parser.add_argument('--satellite', default="foresail1p",
    help="Filter telemetry packets by the satellite identifier/name")
parser.add_argument('--type', dest="packet_type", default="telemetry",
    help="Filter telemetry packets by packet type")
parser.add_argument('--source',
    help="Filter telemetry packets by packet source")
parser.add_argument('--after',
    help="Filter telemetry packets by timestamp")
parser.add_argument('--before',
    help="Filter telemetry packets by timestamp")

# Actions
parser.add_argument('--dry-run', action="store_true", default=False,
    help="Perform just a dry run and read/reformat the packets but don't publish them")

args = parser.parse_args()



def connect_amqp(amqp_url):
    """
        Connect to AMQP
    """
    from urllib.parse import urlparse

    amqp_url = urlparse(amqp_url)
    connection = amqp.Connection(host=amqp_url.hostname, userid=amqp_url.username, password=amqp_url.password)
    connection.connect()
    channel = connection.channel()
    return connection, channel


"""
    Connect
"""
db = PacketsDatabase(args.db_url)
connection, channel = connect_amqp(args.amqp_url or os.getenv("MCC_AMQP_ACCESS"))


"""
    Create telemetry query
"""
constraints = []
if args.satellite:
    constraints.append(f"satellite = {args.satellite!r}")
if args.packet_type is not None:
    constraints.append(f"type = {args.packet_type!r}")
if args.source is not None:
    constraints.append(f"source >= {args.source!r}")
if args.before is not None:
    constraints.append(f"timestamp >= {args.before!r}")
if args.after is not None:
    constraints.append(f"timestamp >= {args.after!r}")
#if args.delta is not None: # TODO: Relative timestamp
#    constraints.append(f"timestamp >= {args.delta!r}")


db.cursor.execute(f"""
    SELECT timestamp, satellite, type, data, metadata
    FROM packets
    WHERE {" AND ".join(constraints)}
    ORDER BY timestamp ASC;
""")


routing_key = 'vc1.tm' # TODO: Where this should be defined?
total_packets = 0

# Build RPC response
for packet in db.cursor.fetchall():

    tm_packet = {
        "timestamp": packet[0].isoformat(),
        "satellite": packet[1],
        "packet_type": packet[2],
        "data": packet[3].hex(),
        "metadata": packet[4],
        "replayed": True,    # Mark that the is replayed and should not be restored to database
    }

    print(tm_packet)
    print()

    if not args.dry_run:
        msg = amqp.basic_message.Message(body=json.dumps(tm_packet))
        channel.basic_publish(msg, exchange='foresail1p', routing_key=routing_key)
        time.sleep(0.1)


print(f"\n{total_packets} packets got replayed!\n")

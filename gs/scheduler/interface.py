#!/usr/bin/env python3
"""
    Command line tool for controlling the scheduler
"""

import json
import argparse

from porthouse.core.rpc import amqp_connect, send_rpc_request


def setup_parser(scheduler_parser: argparse.ArgumentParser) -> None:

    # Filters
    scheduler_parser.add_argument('--satellite',
        help="Filter results by the satellite identifier/name")

    # Actions
    scheduler_parser.add_argument('--print', action="store_true",
        help="")
    scheduler_parser.add_argument('--passes', action="store_true",
        help="")

    scheduler_parser.add_argument('--totals', action="store_true",
        help="Get total number of bytes stored in the database")
    scheduler_parser.add_argument('--export', action="store_true")


def main(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """
    Examples:
    $ porthouse schedule --print
    $ porthouse schedule --passes aalto-1
    """

    #
    # Connect to AMQP broker
    #
    connection, channel = amqp_connect(args.amqp_url)


    if args.print:
        """
    	Print the scheduler schedule
        """

        res = send_rpc_request("scheduler", "rpc.get_schedule", {
            "satellite": "Aalto-1"
        })
        print(json.dumps(res, indent=4))


        print()
        print("SCHEDULE:")
        print("Name:           | Type:           | Metadata:")
        print("----------------|-----------------|-----------------")
        for entry in res["entries"]:
            print(f"{entry['name']:<16}| {entry['type']:<16}|")
        print()


    elif args.passes:
        """
        List all passes
        """
        send_rpc_request("scheduler", "rpc.connect")

        #elif args.scheduler:
        pass

    else:
        parser.print_help()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Scheduler tool')
    setup_parser(parser)
    main(parser, parser.parse_args())

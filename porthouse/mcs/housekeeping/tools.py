"""
Command line tool for accessing the packet database
"""

import amqp
import argparse
import datetime
from typing import List

from .database import HousekeepingDatabase
from porthouse.core.rpc import amqp_connect, send_rpc_request
from porthouse.core.config import load_globals


def setup_parser(packets_parser: argparse.ArgumentParser) -> None:

    packets_parser.add_argument('--create_tables', action="store_true",
        help="If given a default packets table will be created to given the database.")



def main(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """
    Connect SQL database and AMQP broker
    """

    if args.create_tables:
        """
        """

        db = HousekeepingDatabase(
            schema_path="",
            db_url=args.db_url or load_globals().get("db_url", None),
            create_tables=args.create_tables
        )

        #HousekeepingDatabase(
        #    db_url=cfg["db_url"],
        #    schema_path=sys.argv[2],
        #    create_tables=True
        #)

    else:
        parser.print_help()


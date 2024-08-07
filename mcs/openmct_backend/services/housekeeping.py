"""
    Housekeeping backend service
"""
from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Optional, Union
from datetime import datetime, timezone

from porthouse.mcs.housekeeping.database import HousekeepingDatabase, DatabaseError
from ..utils import WebRPCError

class HousekeepingService:

    def __init__(self, server: OpenMCTBackend, db_url: str, satellite: str, hk_schema: str):
        """
        Initialize housekeeping service.
        """
        self.hk_schema = hk_schema
        self.satellite = satellite
        self.server = server
        self.db = HousekeepingDatabase(hk_schema, db_url)


    async def rpc_command(self, client: OpenMCTProtocol, method: str, params: Optional[dict]):
        """
        Handle incoming RPC command.

        Args:
            client: The client object (OpenMCTProtocol)
            method: The RPC method name

        Throws:
            WebRPCError
        """
        if method == "subscribe":
            self.subscribe(client, **params) # type: ignore

        elif method == "unsubscribe":
            self.unsubscribe(client, **params) # type: ignore

        elif method == "get_schema":
            # Maybe not the most beautiful way to access the hk_schema :/
            with open(self.hk_schema, "r") as f:
                return { "schema": json.loads(f.read()) }

        elif method == "request":
            return await self.request_housekeeping(client, params)

        else:
            raise WebRPCError(f"Unknown method {method!r}")


    def subscribe(self, client: OpenMCTProtocol, fields: Union[str, List]) -> None:
        """
        Register a new housekeeping subscription for the client.
        Args:
            client: WebSocket client object
        """

        # If only single field is given, make a list out of it
        if not isinstance(fields, list):
            fields = [ fields ]

        if "housekeeping" not in client.subscriptions:
            client.subscriptions["housekeeping"] = set()
        client_subs = client.subscriptions["housekeeping"]

        for subsystem in fields:
            client_subs.add(subsystem)


    def unsubscribe(self, client: OpenMCTProtocol, fields: Union[str, List[str]]) -> None:
        """
        Unregister housekeeping subscription.

        Args:
            client: WebSocket client object
            params: Parameters received with the RPC command
        """

        if not isinstance(fields, list):
            fields = [ fields ]

        if "housekeeping" not in client.subscriptions:
            return

        # Remove subscriptionss
        client_subs = client.subscriptions["housekeeping"]
        for subsystem in fields:
            if subsystem in client_subs:
                client_subs.remove(subsystem)



    async def handle_subscription(self, message: Dict):
        """
        Distribute new housekeeping to subscribers.

        Args:
            message:
        """

        subsystem = self.satellite + "." + message["subsystem"]

        # Check which clients wants the data
        for client in self.server.clients:
            try:
                client_subs = client.subscriptions["housekeeping"]
            except KeyError:
                continue

            # Check is the subsystem in the subscription list
            if subsystem not in client_subs:
                return None
            print(message["timestamp"])
            await client.send_json(
                subscription={
                    "service": "housekeeping",
                    "subsystem": subsystem,
                    "timestamp": message["timestamp"],
                    "data": message["housekeeping"]
                }
            )


    async def request_housekeeping(self, client: OpenMCTProtocol, params: Dict) -> Dict:
        """
        Request a telemetry history

        Args:
            cl
        """

        """
        params = {
            'subsystem': 'fs1.obc'
            'fields': ['side'],
            'options': {
                'size': 1219,
                'strategy': 'minmax',
                'domain': 'utc',
                'start': 1579878327026,
                'end': 1579879227026
            }
        }
        """

        # Parse satellite name and subsystem
        satellite, subsystem = params["subsystem"].split(".")
        if satellite != self.satellite:
            raise WebRPCError("Wrong satellite")

        fields = params["fields"]
        options = params["options"]

        #
        # Parse options for the SQL query
        #
        request_data = { }
        if "domain" in options and options["domain"] != "utc":
            raise WebRPCError("Invalid domain!")
        if "start" in options:
            request_data["start_date"] = datetime.fromisoformat(options["start"])
        if "end" in options:
            request_data["end_date"] = datetime.fromisoformat(options["end"])

        print("options:", params["options"])
        print("request_data:", request_data)

        strategy = options.get("strategy", None)
        if strategy == "latest":
            #
            # Latest strategy returns only the "latest" housekeeping values inside the time window
            #

            # Execute the database query
            try:
                data = self.db.query_latest(subsystem, fields, **request_data)
            except DatabaseError as e:
                raise WebRPCError("Database error '%s'" % e)
            except TypeError as e:
                if "missing" in str(e):
                    raise WebRPCError("Request missing argument '%s'" % str(e).split("'")[1])
                elif "unexpected" in str(e):
                    raise WebRPCError("Unknown argument '%s'" % str(e).split("'")[1])
                raise

            if data is None:
                return {
                    "subsystem": subsystem,
                    "housekeeping": [ ]
                }

            housekeeping = dict((param, data[param]) for param in fields )
            housekeeping["timestamp"] = data["timestamp"].isoformat()

            return {
                "subsystem": params["subsystem"],
                "housekeeping": [ housekeeping ],
            }

        elif strategy == "minmax":
            #
            # Min/max query which returns all housekeeping values and their minimum and maximum values
            # inside a time window.
            # Given size-parameter specifies the number of bins inside the time window.
            #

            if "size" in options:
                request_data["size"] = options["size"]

            #if fields:
            #    raise WebRPCError("Cannot bucketize enumes")

            # Execute the database query
            try:
                data = self.db.query_binned(subsystem, fields, request_data["start_date"],request_data["end_date"],request_data["size"], generator=True)
            except DatabaseError as e:
                raise WebRPCError("Database error '%s'" % e)
            except TypeError as e:
                if "missing" in str(e):
                    raise WebRPCError("Request missing argument '%s'" % str(e).split("'")[1])
                elif "unexpected" in str(e):
                    raise WebRPCError("Unknown argument '%s'" % str(e).split("'")[1])
                raise

            # Format the query result to a dict
            housekeeping = []
            for row in data:
                print(row)
                entry = dict(
                    (field, {
                        "value": float(row[field + "_avg"]), # psycopg2 might return decimal.Decimal
                        "minValue": row[field + "_min"],
                        "maxValue": row[field + "_max"]
                    }) for field in fields
                )
                entry["timestamp"] = row["timestamp"].isoformat()
                print(entry["timestamp"])
                housekeeping.append(entry)

            return {
                "subsystem": params["subsystem"],
                "housekeeping": housekeeping
            }

        elif strategy is None:
            #
            # No special strategy given so return all values which matches to constraints
            #

            # Execute the database query
            try:
                data = self.db.query(subsystem, fields, generator=True, **request_data)
            except DatabaseError as e:
                raise WebRPCError("Database error '%s'" % e)
            except TypeError as e:
                if "missing" in str(e):
                    raise WebRPCError("Request missing argument '%s'" % str(e).split("'")[1])
                elif "unexpected" in str(e):
                    raise WebRPCError("Unknown argument '%s'" % str(e).split("'")[1])
                raise

            # Format the query result for the OpenMCT friendly format
            housekeeping = []

            for row in data:
                entry = dict((field, row[field]) for field in fields)
                entry["timestamp"] = row["timestamp"].isoformat()
                housekeeping.append(entry)

            return {
                "subsystem": params["subsystem"],
                "housekeeping": housekeeping
            }

        else:
            raise WebRPCError(f"Unknown strategy {options['strategy']!r}" )

"""
    Housekeeping backend service
"""
from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Optional, Union

from porthouse.mcs.housekeeping.database_api import Database, DatabaseError
from ..utils import WebRPCError, iso_timestamp_to_millis, datetime_to_millis, millis_to_datetime

class HousekeepingService:

    def __init__(self, server: OpenMCTBackend, db_url: str, satellite: str, hk_schema: str):
        """
        Initialize housekeeping service.
        """
        self.hk_schema = hk_schema
        self.satellite = satellite
        self.server = server
        self.db = Database(hk_schema, db_url)


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
            self.subscribe(client, **params)

        elif method == "unsubscribe":
            self.unsubscribe(client, **params)

        elif method == "get_schema":
            # Maybe not the most beautiful way to access the hk_schema :/
            with open(self.hk_schema, "r") as f:
                return { "schema": json.loads(f.read()) }

        elif method == "request":
            return await self.request_housekeeping(client, params)

        else:
            raise WebRPCError(f"Unknown method {method!r}")


    def subscribe(self, client: OpenMCTProtocol, fields: Union[str, List]):
        """
        Register a new housekeeping subscription for the client.
        Args:
            client: WebSocket client object
        """

        # If only single field is given, make a list out of it
        if not isinstance(fields, list):
            fields = [ fields ]

        if "housekeeping" not in client.subscriptions:
            client.subscriptions["housekeeping"] = {}
        client_subs = client.subscriptions["housekeeping"]

        for sat, subsystem, field in [ f.split(".") for f in fields]:

            if subsystem not in client_subs:
                client_subs[subsystem] = set()

            client_subs[subsystem].add(field)



    def unsubscribe(self, client: OpenMCTProtocol, fields: Union[str, List[str]]):
        """
        Unregister housekeeping subscription.

        Args:
            client: WebSocket client object
            params: Parameters received with the RPC command
        """

        if not isinstance(fields, list):
            fields = [ fields ]

        if "housekeeping" not in client.subscriptions:
            client.subscriptions["housekeeping"] = {}
        client_subs = client.subscriptions["housekeeping"]

        for sat, subsystem, field in [ f.split(".") for f in fields]:
            if subsystem not in client_subs:
                continue

            # Delete field from the list
            if field in client_subs[subsystem]:
                client_subs[subsystem].remove(field)

            # Delete the subsystem if the subscription is empty
            if len(client_subs[subsystem]) == 0:
                del client_subs[subsystem]


    async def handle_subscription(self, message: Dict):
        """
        Distribute new housekeeping to subscribers.

        Args:
            message:
        """

        subsystem = message["subsystem"]
        timestamp = iso_timestamp_to_millis(message["timestamp"])
        awaits = []

        # Check which clients wants the data
        for client in self.server.clients:
            try:
                client_subs = client.subscriptions["housekeeping"]
            except KeyError:
                continue

            # Check is the subsystem in the subscription list
            if subsystem not in client_subs:
                return None

            # Format the housekeeping data to OpenMCT friendly format
            telemetries = []
            for param, value in message["housekeeping"].items():
                if param in client_subs[subsystem]:
                    telemetries.append({
                        "id":  f"{self.satellite}.{subsystem}.{param}",
                        "timestamp": timestamp,
                        "value": value
                     })

            if len(telemetries) > 0:
                awaits.append( client.send_json(
                    subscription={
                        "service" : "housekeeping",
                        "data": telemetries
                    } ))

        if len(awaits) > 0:
            await asyncio.wait(awaits)


    async def request_housekeeping(self, client: OpenMCTProtocol, params: Dict) -> Dict:
        """
        Request a telemetry history

        Args:
            cl
        """

        """
        params = {
            'key': 'fs1.obc.side',
            'options': {
                'size': 1219,
                'strategy': 'minMax',
                'domain': 'utc',
                'start': 1579878327026,
                'end': 1579879227026
            }
        }
        """

        # Parse telemetry field key list
        if "," in params["key"]:
            params["key"] = params["key"].split(",")
        if isinstance(params["key"], str):
            params["key"] = [ params["key"] ]

        # OpenMCT uses the "fs1.subsystem.param" format.
        # Parse satellite name and subsystem from the first key
        satellite, subsystem = params["key"][0].split(".")[:2]
        if satellite != self.satellite:
            raise WebRPCError("Wrong satellite")

        fields = list([ key.split(".")[-1] for key in params["key"] ])

        options = params["options"]

        """
            Parse options for the SQL query
        """
        request_data = { }
        if "domain" in options and options["domain"] != "utc":
            raise WebRPCError("Invalid domain!")
        if "start" in options:
            request_data["start_date"] = millis_to_datetime(options["start"])
        if "end" in options:
            request_data["end_date"] = millis_to_datetime(options["end"])

        #print("options:", params["options"])
        #print("request_data:", request_data)

        strategy = options.get("strategy", None)
        if strategy == "latest":
            """
                Latest strategy returns only the "latest" housekeeping values inside the time window
            """

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

            return {
                "subsystem": subsystem,
                "housekeeping": [
                    {
                        "id": f"{self.satellite}.{subsystem}.{param}", # TODO: Hack!
                        "timestamp": datetime_to_millis(data["timestamp"]),
                        "value": data[param],
                    } for param in fields
                ]
            }

        elif strategy == "minmax":
            """
                Min/max query which returns all housekeeping values and their minimum and maximum values
                inside a time window.
                Given size-parameter specifies the number of bins inside the time window.
            """

            if "size" in options:
                request_data["size"] = options["size"]

            # Execute the database query
            try:
                data = self.db.query_binned(subsystem, fields, request_data["start_date"],request_data["end_date"],request_data["size"],)
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
                for param in fields:
                    # MinMax wants [value, minValue, maxValue] and openmct does some magic with those
                    housekeeping.append({
                        "id": f"{self.satellite}.{subsystem}.{param}",
                        "timestamp": datetime_to_millis(row["timestamp"]),
                        "value": row[f"{param}_avg"],
                        "minValue": row[f"{param}_min"],
                        "maxValue": row[f"{param}_max"]
                    })

            return {
                "subsystem": subsystem,
                "housekeeping": housekeeping
            }

        elif strategy is None:
            """
               No special strategy given so return all values which matches to constraints
            """

            if "size" in options:
                request_data["size"] = options["size"]

            # Execute the database query
            try:
                data = self.db.query(subsystem, fields, **request_data)
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
                for param in fields:
                    housekeeping.append({
                        "id": f"fs1.{subsystem}.{param}",
                        "timestamp": datetime_to_millis(row["timestamp"]),
                        "value": row[f"{param}"] if (param in row) else row[f"{param}_avg"]
                    })

            return {
                "subsystem": subsystem,
                "housekeeping": housekeeping
            }

        else:
            raise WebRPCError(f"Unknown strategy {options['strategy']!r}" )

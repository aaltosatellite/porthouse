"""
    Events backend service
"""
import asyncio
from ..utils import WebRPCError, iso_timestamp_to_millis
from datetime import datetime

class EventsService:

    def __init__(self, server):
        self.server = server
        self.subscriptions = {}


    async def rpc_command(self, client, method, params):
        """
        """
        print("Got rpc command: ", method, params)
        if method == "subscribe":
            self.subscriptions[client] = True

        elif method == "unsubscribe":
            del self.subscriptions[client]

        elif method == "request":
            return await self.request_events(params)

        else:
            raise WebRPCError(f"Unknown method {method!r}")


    async def request_events(self, params):
        """
        """

        options = params["options"]
        print("request events with options: ",options)

        request_data = { }
        if "domain" in options and options["domain"] != "utc":
            raise WebRPCError("Invalid domain!")
        if "start" in options:
            request_data["start_date"] = options["start"] / 1000
        if "end" in options:
            request_data["end_date"] = options["end"] / 1000

        fields = await self.server.send_rpc_request("events", "rpc.latest", request_data)

        return {
            "subsystem": "events",
            "exchange": "events",
            "entries": [
                {
                    "timestamp": float(param["timestamp"]) * 1000,
                    "source": param["source"],
                    "severity": param["severity"],
                    "data": param["data"],
                    "received": float(param["received"]) * 1000
                } for param in fields["events"]
            ]
        }


    async def handle_subscription(self, message: dict):
        """
        """
        received = datetime.utcnow().isoformat()
        for ev in message["events"]:
            for client in self.subscriptions:
                await client.send_json(
                    subscription={
                        "service": "events",
                        "subsystem": "events",
                        "events": {
                            "id":  "events",
                            "source":  message["source"],
                            "severity": ev["severity"],
                            "event_name": ev["name"],
                            "data": ev["info"],
                            "received": received,
                            "utc": iso_timestamp_to_millis(ev["timestamp"])
                        }
                    }
                )

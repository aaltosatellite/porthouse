"""
    Events backend service
"""
import asyncio
from ..utils import WebRPCError, iso_timestamp_to_millis
from datetime import datetime
from porthouse.mcs.events.database import EventsDatabase, EventsError

class EventsService:

    def __init__(self, server, db_url):
        self.server = server
        self.db = EventsDatabase(db_url)
        self.subscriptions = {}


    async def rpc_command(self, client, method, params):
        """
        """
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

        if "domain" in options and options["domain"] != "utc":
            raise WebRPCError("Invalid domain!")
        
        start = datetime.utcnow().timestamp() - (24 * 3600)  # Default to last 24 hours
        end = datetime.utcnow().timestamp() + (3*3600)
        
    
        if "start" in options:
            start = options["start"] / 1000


        if "end" in options:
            end = options["end"] / 1000


        history = self.db.query(start=start,
                                end=end)


        return {
            "entries": history
        }
    
    async def push_event(self, event: dict):
        """
        Push an event to the database.
        """
        event["received"] = datetime.utcnow().isoformat()
        # Check if event has all required fields
        required_fields = ["timestamp", "severity", "info", "name"]
        if not "source" in event:
            raise EventsError("Event is missing 'source' field")
        for ev in event["events"]:
            # Ensure each event has the required fields
            for ev_field in required_fields:
                if ev_field not in ev:
                    raise EventsError(f"Event is missing required field: {ev_field}")
            
            # Convert timestamps to ISO format if they are not already
            if isinstance(ev["timestamp"], (int, float)):
                ev["timestamp"] = datetime.fromtimestamp(ev["timestamp"]).isoformat()
            if isinstance(event["received"], (int, float)):
                event["received"] = datetime.fromtimestamp(ev["received"]).isoformat()

            print("Inserting event:", ev)
            print("With timestamp:", ev["timestamp"])
            # Insert each event into the database
            self.db.insert_event(
                timestamp=ev["timestamp"],
                received=event["received"],
                severity=ev["severity"],
                data=ev["info"],
                event_name=ev["name"],
                source=event["source"]
            )


    async def handle_subscription(self, message: dict):
        """
        """
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
                            "received": message["received"],
                            "utc": iso_timestamp_to_millis(ev["timestamp"])
                        }
                    }
                )

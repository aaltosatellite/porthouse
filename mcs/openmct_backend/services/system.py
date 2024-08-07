"""
    System (logging) subscription support subscriptions and requests
"""
import asyncio
from ..utils import WebRPCError

class SystemService:

    def __init__(self, server):
        self.server = server
        self.subscription = {}


    async def rpc_command(self, client, method, params):
        """ Handle RPC command """

        if method == "subscribe":
            self.subscription[client] = True

        elif method == "unsubscribe":
            del self.subscription[client]

        elif method == "request":
            return await self.request_log_history(client, params)

        else:
            raise WebRPCError(f"No such method {method!r}")


    async def request_log_history(self, client, params):
        """
            Request Logs
        """
        # Returns logs within a given time span. Notice that mcc's log support is what it is, so only
        # those logs that are currently loaded are obtainable. Logs are stored into a files so they are not
        # obtainable without additional programming.

        options = params["options"]

        request_data = {}
        if "domain" in options and options["domain"] != "utc":
            raise WebRPCError("Invalid domain!")
        if "start" in options:
            request_data["start_date"] = options["start"]
        if "end" in options:
            request_data["end_date"] = options["end"]

        fields = await self.server.send_rpc_request("log", "rpc.get_history")

        return {
            "subsystem": "log",
            "exchange": "logs",
            "entries": [
                {
                    "created": param["created"],
                    "module": param["module"],
                    "level": param["level"],
                    "message": param["message"],
                } for param in fields["entries"]
            ]
        }


    async def handle_subscription(self, message):
        """
        """

        msg = {
            "subscription": {
                "subsystem": "log",
                "exchange": "logs",
                "log": {
                    "module": message["module"],
                    "level": message["level"],
                    "created": message["created"],
                    "message": message["message"]
                }
            }
        }

        awaits = []
        for client in self.subscription:
            awaits.append( client.send_json(msg) )
        if len(awaits) > 0:
            await asyncio.wait(awaits)

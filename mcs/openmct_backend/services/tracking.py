# Tracking support returns TLE's. Does not support subscriptions
# TODO: is cache required? I don't want the openmct backend bombard mcc with TLE requests.

from ..utils import WebRPCError

class TrackingService:

    def __init__(self, server):
        """ Initialize Tracking service """
        self.server = server
        self.subscriptions = { }

    async def rpc_command(self, client, method, params):

        if method == "subscribe":
            self.subscriptions[client] = True

        elif method == "unsubscribe":
            del self.subscriptions[client]

        elif method == "get_tle":
            return await self.get_tle(params)

        else:
            raise WebRPCError(f"No such method: {method}")


    async def get_tle(self, params=None):
        """
            Come up a way to access rpc request better
            Returns requested TLEs as neat dict structure.
        """

        keys = list(params.keys())
        #print("params", keys)

        trackables = []

        # TLE server only brings one at a time
        for key in keys:

            res = await self.server.send_rpc_request("tracking", "tle.rpc.get_tle",
                {"satellite": key})

            trackables.append({
                "name": res["name"],
                "tle1": res["tle1"],
                "tle2": res["tle2"]
            })

        return {
            "subsystem": "tracking",
            "exhange": "tracking",
            "trackables": trackables
        }

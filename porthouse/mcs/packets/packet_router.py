"""
    Packet router module
"""

import json
import asyncio
from importlib import import_module
from typing import Any, Callable, Dict, List, Optional

import zmq
import zmq.asyncio

from porthouse.core.basemodule_async import BaseModule, rpc, RPCError, bind
from .router_endpoints import *


class Endpoint:
    name: str
    source: Optional[str]
    satellite: Optional[str]
    link: Optional['Endpoint']
    formatter: Optional[Callable]
    metadata: Dict
    persistent: bool



class PacketRouter(BaseModule):
    """
        A module to listen different packets from multiple sources and
        archive them to database. Responds also packet RPCs.
    """

    endpoints: Dict[str, Endpoint]

    def __init__(self, endpoints: List[Dict[str, Any]], routes: List[str], **kwargs):
        """
        Initialise module
        """
        BaseModule.__init__(self, **kwargs)
        self.zmq_ctx = zmq.asyncio.Context()


        self.endpoint_factors = {
            "amqp-out": Outgoing_AMQP_Endpoint,
            "amqp-in": Incoming_AMQP_Endpoint,
            "zmq-sub": ZMQ_Subscriber_Endpoint,
            "zmq-pub": ZMQ_Publisher_Endpoint,
            "udp-out": Outgoing_UDP_Endpoint,
            "udp-in": Incoming_UDPEndpoint,
            "tcp": TCPEndpoint,
        }

        self.endpoints = { }

        loop = asyncio.get_event_loop()
        loop.create_task(self.load_endpoints(endpoints, routes))


    @rpc()
    @bind('packets', 'router.rpc.#', prefixed=True)
    def rpc_handler(self,
            request_name: str,
            request_data: Dict[str, Any]
        ) -> Optional[Dict[str, Any]]:
        """
        Remote Procedure Calls
        """

        self.log.debug("RPC: %s ", request_name)

        if request_name == "router.rpc.list":
            """
                List all endpoints and links
            """

            pretty_endpoints = list([
                {
                    "name": e.name,
                    "type": e.type_identifier,
                } for e in self.endpoints.values()
            ])

            pretty_routers = list([
                {
                    "source": endpoint.name,
                    "destination": endpoint.link.name
                } for endpoint in self.endpoints.values() if endpoint.link is not None
            ])

            return {
                "endpoints": pretty_endpoints,
                "routes": pretty_routers,
            }

        elif request_name == "router.rpc.connect":
            """
                Connect two endpoints
            """
            try:
                self.create_route(request_data["a"], request_data["b"])
            except Exception as e:
                self.log.error(f"Error while connecting route!: {e.args[0]}", exc_info=True)
                raise RPCError(e.args[0])

        elif request_name == "router.rpc.disconnect":
            """
                Disconnect two endpoint
            """
            try:
                self.create_route(request_data["a"], None)
            except Exception as e:
                self.log.error(f"Error while disconnecting route!: {e.args[0]}", exc_info=True)
                raise RPCError(e.args[0])

        elif request_name == "router.rpc.disconnect_all":
            """
                Disconnect all links
            """
            pass


    async def load_endpoints(self,
            endpoints: List[Dict[str, Any]],
            routes: List[str]
        ) -> None:
        """
        Create message queue and attach it to given exchanges
        """

        # For each endpoint definition string
        for endpoint_params in endpoints:
            endpoint_name = endpoint_params.pop("name")

            # Parse endpoint configuration
            try:
                # Get the endpoint class instance
                endpoint_type = endpoint_params.pop('type')
                endpoint_class = self.endpoint_factors.get(endpoint_type, None)
                if endpoint_class is None:
                    self.log.warning(f"Unknown endpoint type {endpoint_type}")
                    continue

                self.log.debug("Creating new endpoint '%s' (type: %s)", endpoint_name, endpoint_type)
                persistent = endpoint_params.pop("persistent", "True").lower() == "true"
                formatter = endpoint_params.pop("formatter", None)
                metadata = endpoint_params.pop("metadata", { })
                source = endpoint_params.pop("source", None)
                satellite = endpoint_params.pop("satellite", None)

                # Create new instance
                inst = self.endpoints[endpoint_name] = endpoint_class(self, **endpoint_params)
                inst.name = endpoint_name
                inst.link = None
                inst.persistent = persistent
                inst.formatter = None
                inst.metadata = metadata
                inst.source = source
                inst.satellite = satellite

                # Parse formatter function
                if formatter:
                    module, func = formatter.rsplit('.', 1)
                    inst.formatter = getattr(import_module(module), func)

                # Connect the endpoint if its autoconnecting one
                if persistent and hasattr(inst, "connect"):
                    inst.connected = True
                    result = inst.connect()
                    if hasattr(result, "__await__"):
                        await result


            except ModuleNotFoundError:
                self.log.error(f"Cannot import formatter module %r", formatter, exc_info=True)

            except KeyError as e:
                self.log.error(f"Missing parameter {e} from endpoint configuration {endpoint_params!r} ", exc_info=True)

            except ValueError as e:
                self.log.error(f"Malformed endpoint configuration. ValueError {e}: {endpoint_params!r}", exc_info=True)



        # For each link definition string
        for route_def in routes:

            # Parse link parameter string
            try:
                endpoint_a, endpoint_b = [ params.strip() for params in route_def.split(">") ]
            except:
                self.log.error(f"Malformed route configuration: {route_def!r}")
                continue

            # Parse link configuration
            self.create_route(endpoint_a, endpoint_b)


    def create_route(self, endpoint_a: str, endpoint_b: str) -> None:
        """
        Create or remote new route from endpoint A (to endpoint B)

        Args:
            endpoint_a:
            endpoint_b:

        """

        if endpoint_a == endpoint_b:
            raise ValueError("Loop")

        try:
            a = self.endpoints[endpoint_a]
            if endpoint_b is not None:
                b = self.endpoints[endpoint_b]
            else:
                b = None
        except KeyError as e:
            self.log.error(f"Endpoint {e} not found!")
            raise RuntimeError(f"Endpoint {e} not found!")

        # Remove old route from A if such exists
        if a.link is not None:
            self.log.info(f"Removed route: {endpoint_a} -> {a.link.name}")
            a.link = None

            #if a.connected and not a.pesistent:
            #    a.disconnect()

        # Create new route if new endpoint was given
        if b is not None:
            a.link = b
            self.log.info(f"Created new route: {endpoint_a} -> {endpoint_b}")


    def route_frame(self, source: Endpoint, raw_frame: bytes) -> None:
        """
        Route received frame to corresponding outgoing endpoint
        """

        try:

            destination = source.link
            if destination is None:
                self.log.warning(f"Got a frame from {source.name!r} but there is no connection forward")
                return

            # Apply the input formatter
            if source.formatter:
                frame: dict = source.formatter(raw_frame)
            else:
                frame: dict = json.loads(raw_frame)

            # Possible inparseable frame or a control frame so skip it
            if frame is None:
                return

            # Merge all metadata field with priority
            metadata = source.metadata.copy()
            metadata.update(destination.metadata)
            metadata.update(frame.get("metadata", {}))
            frame["metadata"] = metadata

            frame["source"] = frame.get("source", source.source)
            frame["satellite"] = frame.get("satellite", source.satellite)

            # Apply the output formatter
            if destination.formatter:
                frame = destination.formatter(frame)
            else:
                frame = json.dumps(frame).encode("ascii")

            self.log.debug(f"Routing frame {source.name} --> {destination.name}")

            if not hasattr(destination, "send"):
                self.log.warning(f"Destination endpoint {destination.name} is not capable to send!")
                return

            # Send it forward
            result = destination.send(frame)
            if hasattr(result, "__await__"):
                asyncio.create_task(result)

        except:
            self.log.error("Failed to route packet! Unknown error", exc_info=True)


if __name__ == "__main__":
    PacketRouter(
        endpoints=[
        {
            "name:": "uplink",
            "type": "zmq-pub",
            "connect": "tcp://127.0.0.1:52101",
            "packet_type": "raw_tc",
            "source": "oh2ags",
            "formatter": "router_formatter_raw.json_to_raw"
        },
        {
            "name": "downlink",
            "type": "zmq-sub",
            "connect": "tcp://127.0.0.1:52001",
            "packet_type": "raw_tm",
            "source": "oh2ags",
            "formatter": "router_formatter_raw.raw_to_json"
        },
        {
            "name": "foresail1p_tc",
            "type": "amqp-in",
            "packet_type": "telecommand",
            "exchange": "foresail1p",
            "routing_key": "*.tc"
        },
        {
            "name": "foresail1p_tm",
            "type": "amqp-out",
            "packet_type": "telemetry",
            "exchange": "foresail1p",
            "routing_key": "*.tm"
        }
        ],
        routes= [
            "foresail1p_tc > uplink",
            "downlink > foresail1p_tm",
        ],
        amqp_url="amqp://guest:guest@localhost:5672/",
        debug=True
    ).run()

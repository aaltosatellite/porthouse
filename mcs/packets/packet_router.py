"""
    Packet router module

    Example endpoint definitions:
        endpoint_aalto_up = "type=zmq-pub, connect=tcp://127.0.0.1:52100, source=oh2ags"
        endpoint_aalto_down = "type=zmq-sub, connect=tcp://127.0.0.1:52000, source=oh2ags"
        endpoint_foresail1_tc = "type=amqp-out, exchange=foresail1, routing_key=tc"
        endpoint_foresail1_tm= " type=amqp-in, exchange=foresail1, routing_key=tm"
"""

import json
import asyncio
from importlib import import_module
from typing import Any, Dict, List, Optional

import zmq
import zmq.asyncio

from porthouse.core.basemodule_async import BaseModule, queue, rpc, RPCError, bind
from .router_endpoints import *


class PacketRouter(BaseModule):
    """
        A module to listen different packets from multiple sources and
        archive them to database. Responds also packet RPCs.
    """

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
            endpoint_name = endpoint_params.get("name")

            # Parse endpoint confguration
            try:
                # Get the endpoint class instance
                endpoint_type = endpoint_params.pop('type')
                endpoint_class = self.endpoint_factors.get(endpoint_type, None)
                if endpoint_class is None:
                    self.log.warning(f"Unknwon endpoint type {endpoint_type}")
                    continue

                self.log.debug("Creating new endpoint '%s' (type: %s)", endpoint_name, endpoint_type)
                persistent = endpoint_params.pop("persistent", "true").lower() == "true"

                formatter = endpoint_params.pop("formatter", None)

                # Parse additional metadta
                additional_metadata = {}
                for name in endpoint_params.keys():
                    if name.startswith("metadata:"):
                        additional_metadata[name[9:]] = endpoint_params.pop(name)
                #endpoint_params["metadata"] = additional_metadata
                #self.log.debug("Metadata: %s", json.dumps(endpoint_params))

                # Create new instance
                inst = self.endpoints[endpoint_name] = endpoint_class(self, **endpoint_params)
                inst.name = endpoint_name
                inst.link = None
                inst.persistent = persistent
                inst.formatter = None

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

            # Parse link paramater string
            try:
                endpoint_a, endpoint_b = [ params.strip() for params in route_def.split(">") ]
            except:
                self.log.error(f"Malformed route configuration: {route_def!r}")
                continue

            # Parse link confguration
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


    def route_frame(self, source: str, frame: bytes) -> None:
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
                frame = source.formatter(frame)
            else:
                frame = json.loads(frame)

            # Possible inparseable frame or a dummy frame so skip it
            if frame is None:
                return

            # Add additional fields
            new_frame = source.additional_data.copy()
            new_frame.update(destination.additional_data)
            new_frame.update(frame)
            # TODO: Join metadata fields

            # Apply the output formatter
            if destination.formatter:
                new_frame = destination.formatter(new_frame)
            else:
                new_frame = json.dumps(new_frame).encode("ascii")

            self.log.debug(f"Routing frame {source.name} --> {destination.name}")

            if not hasattr(destination, "send"):
                self.log.warning(f"Destination endpoint {destination.name} is not capable to send!")
                return

            # Send it forward
            result = destination.send(new_frame)
            if hasattr(result, "__await__"):
                asyncio.create_task(result)

        except:
            self.log.error("Failed to route packet! Unknown error", exc_info=True)


if __name__ == "__main__":
    PacketRouter(
#        endpoint_aalto_up="type=zmq-sub, connect=tcp://127.0.0.1:43701, packet_type=raw_tc, source=oh2ags, formatter=router_formatter_suo.from_suo",
#        endpoint_aalto_down="type=zmq-sub, connect=tcp://127.0.0.1:43700, packet_type=raw_tm, source=oh2ags, formatter=router_formatter_suo.from_suo",

        endpoint_aalto_up="type=zmq-pub, connect=tcp://127.0.0.1:52101, packet_type=raw_tc, source=oh2ags, formatter=router_formatter_raw.json_to_raw",
        endpoint_aalto_down="type=zmq-sub, connect=tcp://127.0.0.1:52001, packet_type=raw_tm, source=oh2ags, formatter=router_formatter_raw.raw_to_json",
        endpoint_aalto2_down="type=zmq-sub, connect=tcp://127.0.0.1:52003, packet_type=raw_tm, source=oh2ags, formatter=router_formatter_raw.raw_to_json",

        endpoint_egse_up="type=zmq-pub, connect=tcp://127.0.0.1:53001, packet_type=raw_tc, source=egse, formatter=router_formatter_raw.json_to_raw",
        endpoint_egse_down="type=zmq-sub, connect=tcp://127.0.0.1:53000, packet_type=raw_tm, source=egse, formatter=router_formatter_raw.raw_to_json",


        #endpoint_raw_up="type=zmq-sub, connect=tcp://127.0.0.1:43701, source=oh2ags",

        endpoint_foresail1_tc="type=amqp-in, packet_type=telecommand, exchange=foresail1, routing_key=*.tc",
#        endpoint_foresail1_tc="type=amqp-in, packet_type=telecommand, exchange=foresail1, routing_key=*.tc",
        endpoint_foresail1_tm="type=amqp-out, packet_type=telemetry, exchange=foresail1, routing_key=*.tm",
#        endpoint_json="type=zmq-sub, packet_type=blaaa, bind=tcp://*:57000, source=json",
#
        route_1="foresail1_tc > aalto_up",
        route_2="aalto_down > foresail1_tm",
        route_3="aalto2_down > foresail1_tm",

#        route_4="foresail1_tc > egse_up",
        route_5="egse_down > foresail1_tm",

        #route_3="raw_up > raw_db",
        #route_4="raw_down > raw_db",

#        route_5="json > foresail1_tm",

        amqp_url="amqp://guest:guest@localhost:5672/",
        debug=True
    ).run()

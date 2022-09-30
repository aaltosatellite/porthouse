"""
    Packet storage module

    Example link definitions:
        "satellite=fs1, packet_type=downlink, source=OH2AGS, type=zmq, connect=tcp://127.0.0.1:8888"
        "satellite=aalto1, packet_type=uplink, source="OH2AGS, type=amqp, exchange=modem, routing_key=aalto1.uplink"

"""


import asyncio
import json
import functools
from datetime import datetime, timezone
from typing import Any, Dict, List
import zmq
import zmq.asyncio

from porthouse.core.basemodule_async import BaseModule, queue, rpc, bind, RPCError
from .database_api import PacketsDatabase







class PacketStorage(BaseModule):
    """
        A module to listen different packets from multiple sources and
        archive them to database. Responds also packet RPCs.
    """

    def __init__(self,
            db_url: str,
            links: List[Dict[str, Any]],
            **kwargs):
        """
        Initialise module
        """
        BaseModule.__init__(self, **kwargs)
        self.links = {}

        self.db = PacketsDatabase(db_url)
        self.zmq_ctx = None

        loop = asyncio.get_event_loop()
        loop.create_task(self.create_links(links))


    @rpc()
    @bind('packets', 'rpc.#', prefixed=True)
    def rpc_handler(self, request_name: str, request_data: Dict[str, Any]):
        """
        Remote Procedure Calls

        Args:
            request_name:
            request_data:
        """

        self.log.debug("RPC: %s ", request_name)

        if request_name == "rpc.list":
            """
                Request packets form the database
            """

            try:
                packets = []
                for packet in self.db.query(**request_data):
                    packet["data"] = packet.get("data", "").hex()
                    packet["timestamp"] = packet.get("timestamp", datetime.now(timezone.utc)).isoformat()
                    packets.append(packet)
            except TypeError as e:
                if "missing" in str(e):
                    raise RPCError("Request missing argument '%s'" % str(e).split("'")[1])
                elif "unexpected" in str(e):
                    raise RPCError("Unknown argument '%s'" % str(e).split("'")[1])
                raise

            return {
                "satellite": request_data["satellite"],
                "packets": packets
            }

        elif request_name == "rpc.satellites":
            """
                Get list of satellites in the database
            """

            response = []
            self.db_cursor.execute(
                "SELECT satellite, COUNT(*) FROM packets GROUP BY satellite", request_data)
            for name, packets in self.db_cursor.fetchall():
                response.append({"name": name, "packets": packets})
            return {"satellites": response}

        elif request_name == "rpc.import":
            pass


    async def create_links(self, links):
        """
            Create message queue and attach it to given exchanges
        """

        # For each link definition string
        for link_params in links:

            # Parse link confguration
            try:

                link_type = link_params.get("type")
                if link_type == "amqp":
                    """
                    Create AMQP link
                    """

                    try:

                        exchange, routing_key = link_params.get("exchange"), link_params.get("routing_key")

                        # Create queue for incoming packet
                        declare_ok = await self.channel.queue_declare(exclusive=True)
                        await self.channel.basic_consume(declare_ok.queue,
                            functools.partial(self.amqp_data_callback, additional_data=link_params))

                        # Bind to AMQP queue
                        await self.channel.queue_bind(queue=declare_ok.queue, exchange=exchange, routing_key=routing_key)

                        self.log.debug(f"Added AMQP link {exchange}/{routing_key}")

                    except:
                        self.log.error(f"Failed to create AMQP link {exchange}/{routing_key}", exc_info=True)


                elif link_type == "zmq":
                    """
                    Create ZMQ link
                    """

                    # Create ZMQ if one doesn't exist
                    if self.zmq_ctx is None:
                        self.zmq_ctx = zmq.asyncio.Context()

                    # Create socket and bind/connect it
                    sock = self.zmq_ctx.socket(zmq.SUB)
                    if "connect" in link_params:
                        sock.connect(link_params.get("connect"))
                    elif "bind" in link_params:
                        sock.bind(link_params.get("bind"))
                    else:
                        raise ValueError("Invalid ZMQ connection parameter")

                    sock.setsockopt(zmq.SUBSCRIBE, link_params.get("subscribe", "").encode("ascii"))

                    # Create listener task
                    asyncio.get_event_loop().create_task(self.zmq_data_receiver(sock, link_params))
                    self.log.debug(f"Added ZMQ link {link_params}")

                else:
                    self.log.error(f"Unknown link type: {link_type}")


            except KeyError as e:
                self.log.error(f"Missing parameter {e} from link configuration {link_params!r} ", exc_info=True)

            except ValueError as e:
                self.log.error(f"Malformed link configuration. ValueError {e}: {link_params!r}", exc_info=True)


    def parse_json_frame_to_db(self, msg, addtional_params):
        """
        Parse JSON frame ready to database
        """

        try:
            packet = json.loads(msg)
            if packet.get("replayed", False):
                return

            # Parse hexadecimal string to bytes
            packet["data"] = bytes.fromhex(packet["data"])

            # Metge packet and additional fields dict
            pp = addtional_params.copy()
            pp.update(packet)
            packet = pp

            self.db.store_packet(**packet)

            self.log.debug("New packet %s %s: (%d bytes)", packet["satellite"], packet["packet_type"], len(packet["data"]))

        except KeyError as e:
            self.log.error(f"Incoming packet missing field {e!r}: {msg!r}", exc_info=True)

        except TypeError as e:
            if "missing" in str(e) and "argument" in str(e):
                self.log.error("Incoming packet missing field %r" % str(e).split("'")[1], exc_info=True)
            else:
                self.log.error(f"Failed to parse incoming frame {msg!r}", exc_info=True)

        except:
            self.log.error(f"Failed to parse incoming frame {msg!r}", exc_info=True)


    async def amqp_data_callback(self, message, additional_data):
        """
            AMQP callback to store packet to database
        """
        self.parse_json_frame_to_db(message.body, additional_data)


    async def zmq_data_receiver(self, sock, additonal_data, **kwargs):
        """
        Async data receiver for ZMQ sockets
        """
        while True:
            packet = await sock.recv()
            self.parse_json_frame_to_db(packet, additonal_data)


if __name__ == "__main__":
    PacketStorage(
        links = [
            { "name": "", "satellite": "foresail1", "type": "zmq", "connect": "tcp://127.0.0.1:56000" },
            { "name": "tc", "satellite": "foresail1", "packet_type": "telecommand", "type": "amqp", "exchange": "foresail1", "routing_key": "*.tc" },
            { "name": "tm", "satellite": "foresail1", "packet_type": "telemetry", "type": "amqp", "exchange": "foresail1", "routing_key": "*.tm" },
        ],
        db_url="postgres://mcs:PASSWORD@localhost/foresail",
        amqp_url="amqp://guest:guest@localhost:5672/",
        debug=True
    ).run()


import asyncio
import aiormq
import zmq
import zmq.asyncio

import socket
from typing import NoReturn, Optional, Tuple, Union



class ZMQ_Subscriber_Endpoint:
    """
        Endpoint class to attach ZMQ sockets
    """
    type_identifier = "zmq-sub"

    def __init__(self,
            m,
            bind: Optional[str]=None,
            connect: Optional[str]=None,
            subscribe: str="",
            multipart: bool=False,
            **kwargs
        ):
        """
        Initalize ZMQ subscriber endpoint
        Args:
            bind: Address used for binding
            connect: Address used for connecting
            subcribe: Optional subscriber topic filter
            multipart: If true the socket .
            kwargs: Additional keyword arguments will be passed as additional data.

        Remarks:
            If multipart is used, the received and transmitted packet objects are
            always tuples containing the bytes object. Formatter supporting this must be used!
        """
        self.m = m
        self._subscribe = subscribe
        self._bind = bind
        self._connect = connect
        self.multipart = multipart
        self.additional_data = kwargs
        self.task = None
        self.closing: Optional[asyncio.Future] = None
        self.sock: Optional[zmq.socket] = None

    def connect(self) -> None:
        """ Create ZMQ socket, bind/connect it and subscribe """

        # Create socket and bind/connect it
        self.sock = self.m.zmq_ctx.socket(zmq.SUB)
        if self._connect is not None:
            self.sock.connect(self._connect)
        elif self._bind is not None:
            self.sock.bind(self._bind)
        else:
            raise ValueError("No connect nor bind parameter given")

        if self._subscribe is not None:
            self.sock.setsockopt(zmq.SUBSCRIBE, self._subscribe.encode("ascii"))

        loop = asyncio.get_event_loop()
        self.closing = loop.create_future()

        # Create listener task
        self.task = loop.create_task(self._receiver())

    def disconnect(self) -> None:
        """ Disconnect the subsriber socket """
        print("ZMQ Subscriber disconnect")
        self.closing.set_result(0)
        self.sock.close()
        del self.sock

    async def _receiver(self) -> NoReturn:
        """ ZMQ receiver task  """
        try:
            while not self.closing.done():
                packet = await (self.sock.recv_multipart() if self.multipart else self.sock.recv())
                self.m.route_frame(self, packet)
        except:
            import traceback
            traceback.print_exc()

    def __repr__(self) -> str:
        return "ZMQSubscriberEndpoint"




class ZMQ_Publisher_Endpoint:
    """
        Endpoint class to publish ZMQ socket
    """
    type_identifier = "zmq-pub"

    def __init__(self, m,
            bind: Optional[str]=None,
            connect: Optional[str]=None,
            multipart: bool=False,
            **kwargs
        ):
        """
        """
        self.m = m
        self._bind = bind; self._connect = connect
        self.multipart = multipart
        self.additional_data = kwargs
        self.sock: Optional[zmq.socket] = None
        self.closing: Optional[asyncio.Future] = None

    def connect(self) -> None:
        """ Create ZMQ socket and bind/connect it """

        self.sock = self.m.zmq_ctx.socket(zmq.PUB)
        if self._connect is not None:
            self.sock.connect(self._connect)
        elif self._bind is not None:
            self.sock.bind(self._bind)
        else:
            raise ValueError("No connect nor bind parameter given")

        loop = asyncio.get_event_loop()
        self.closing = loop.create_future()

    def disconnect(self) -> None:
        """ Disconnect the publisher socket """
        self.closing.set_result(0) # Stop the receiver loop
        self.sock.close()
        del self.sock

    async def send(self, pkt: Union[bytes, Tuple[bytes]]) -> None:
        """ Send frame to ZMQ pub/sub socket """
        await (self.sock.send_multipart(pkt) if self.multipart else self.sock.send(pkt))

    def __repr__(self) -> str:
        return "ZMQPublisherEndpoint"



class Outgoing_AMQP_Endpoint:
    """
        Endpoint class to attach AMQP topics
    """
    type_identifier = "amqp-out"

    def __init__(self, m, exchange: str, routing_key: str, **kwargs):
        """
        Args:
            exchange:
            routing_key:
            kwargs: Additional keyword arguments will be added to as additional data
        """

        self.m = m
        self._exchange = exchange
        self._routing_key = routing_key
        self.additional_data = kwargs

    async def send(self, pkt) -> None:
        """ Send packet to AMQP exchange """
        await self.m.channel.basic_publish(pkt, exchange=self._exchange, routing_key=self._routing_key)


class Incoming_AMQP_Endpoint:
    """
        Endpoint class to attach AMQP topics
    """
    type_identifier = "amqp-in"

    def __init__(self, m, exchange: str, routing_key: str, **kwargs):
        """
        """
        self.m = m
        self._exchange = exchange
        self._routing_key = routing_key
        self.additional_data = kwargs
        self.queue_name = None

    async def connect(self) -> None:
        """ Create new queue for incoming frames """
        declare_ok = await self.m.channel.queue_declare(exclusive=True)
        self.queue_name = declare_ok.queue
        await self.m.channel.basic_consume(declare_ok.queue, consumer_callback=self.receiver_callback, no_ack=True)
        await self.m.channel.queue_bind(declare_ok.queue, exchange=self._exchange, routing_key=self._routing_key)

    async def disconnect(self) -> None:
        """ """
        await self.m.channel.queue_delete(self.queue_name)
        self.queue_name = None

    async def receiver_callback(self, pkt: aiormq.types.DeliveredMessage) -> None:
        """ """
        self.m.route_frame(self, pkt.body)


class Outgoing_UDP_Endpoint:
    """
        UCP Endpoint for the packet router
    """
    type_identifier = "udp-out"
    def __init__(self, m, connect, **kwargs):
        self.m = m
        self.uconnect = connect
        self.additional_data = kwargs
        self.sock: Optional[socket.socket] = None

    def connect(self) -> None:
        """ """
        host, port = self.uconnect.split(":")
        port = int(port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host,port))

    async def send(self, pkt):
        """ """
        if not isinstance(pkt, bytes):
            raise ValueError(f"UDP can send only byte decoded packets! {type(pkt)} given")
        await self.sock.sendto(pkt, 2)


class Incoming_UDPEndpoint:
    """
        UCP Endpoint for the packet router
    """
    type_identifier = "udp-in"
    def __init__(self, m, bind: str, **kwargs):
        self.m = m
        host, port = self.bind.split(":")

        self.additional_data = kwargs
        self.sock: Optional[socket.socket] = None

    def connect(self) -> None:
        """
        """
        loop = asyncio.get_event_loop()
        self.sock = socket.socket()
        self.sock.bind()
        loop.add_reader(self.sock, self._received_callback)

    async def disconnect(self) -> None:
        """ Disconnect the UDP socket """
        loop = asyncio.get_event_loop()
        loop.remove_reader(self.sock)
        self.sock.close()

    async def _received_callback(self) -> None:
        packet = await self.sock.recv()
        self.m.route_frame(self, packet)


class TCPEndpoint:
    """
    TCP Endpoint for the packet router
    """

    type_identifier = "tcp"

    def __init__(self,
            bind: Optional[str]=None,
            connect: Optional[str]=None,
            **kwargs
        ):
        """

        Args:
            bind:
            connect:
        """
        self._bind = bind
        self._connect = connect
        self._additional_data = kwargs
        self._client = None

    async def connect(self):
        """ Make new TCP server/client """

        loop = asyncio.get_current_event_loop()
        if self._bind is not None:
            host, port = self._bind.split(":")

            await loop.create_server(self._protocol_factory, host, int(port))

        elif self.connect is not None:
            pass
        else:
            raise ValueError("Neither bind or connect!")

    def _protocol_factory(self):
        if self.client:
            pass

    async def disconnect(self):
        """ Disconnect the TCP socket(s) """
        self.closing.set_result(0) # Stop the receiver loop
        self.sock.close()

    async def send(self, pkt) -> None:
        """ Send frame """
        if not isinstance(pkt, bytes):
            raise ValueError(f"TCP can send only byte decoded packets! {type(pkt)} given")
        self.sock.send(pkt, 2)

    async def received_callback(self, pkt):
        """ New packet from the TCP Client """
        self.m.route_frame(self, pkt)

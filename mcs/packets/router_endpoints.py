
import asyncio
import aiormq
import zmq
import zmq.asyncio

import socket
from typing import List, NoReturn, Optional, Tuple, Union



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
            multipart: If true, the ZMQ multipart messages will be used.

        Remarks:
            If multipart is used, the received and transmitted packet objects are
            always tuples containing the bytes object. Formatter supporting this must be used!
        """
        self.m = m
        self._subscribe = subscribe
        self._bind = bind
        self._connect = connect
        self._multipart = multipart
        self._task = None
        self._closing: Optional[asyncio.Future] = None
        self._sock: Optional[zmq.socket] = None

    def connect(self) -> None:
        """ Create ZMQ socket, bind/connect it and subscribe """

        # Create socket and bind/connect it
        self._sock = self.m.zmq_ctx.socket(zmq.SUB)
        if self._connect is not None:
            self.sock.connect(self._connect)
        elif self._bind is not None:
            self._sock.bind(self._bind)
        else:
            raise ValueError("No connect nor bind parameter given")

        if self._subscribe is not None:
            self._sock.setsockopt(zmq.SUBSCRIBE, self._subscribe.encode("ascii"))

        loop = asyncio.get_event_loop()
        self._closing = loop.create_future()

        # Create listener task
        self._task = loop.create_task(self._receiver())

    def disconnect(self) -> None:
        """ Disconnect the subsriber socket """
        print("ZMQ Subscriber disconnect")
        self._closing.set_result(0)
        self._sock.close()
        del self._sock

    async def _receiver(self) -> NoReturn:
        """ ZMQ receiver task  """
        try:
            while not self._closing.done():
                packet = await (self._sock.recv_multipart() if self.multipart else self._sock.recv())
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
            multipart: bool=False
        ):
        """
        """
        self.m = m
        self._bind = bind; self._connect = connect
        self._multipart = multipart
        self._sock: Optional[zmq.socket] = None
        self._closing: Optional[asyncio.Future] = None

    def connect(self) -> None:
        """ Create ZMQ socket and bind/connect it """

        self._sock = self.m.zmq_ctx.socket(zmq.PUB)
        if self._connect is not None:
            self._sock.connect(self._connect)
        elif self._bind is not None:
            self._sock.bind(self._bind)
        else:
            raise ValueError("No connect nor bind parameter given")

        loop = asyncio.get_event_loop()
        self._closing = loop.create_future()

    def disconnect(self) -> None:
        """ Disconnect the publisher socket """
        self._closing.set_result(0) # Stop the receiver loop
        self._sock.close()
        del self._sock

    async def send(self, pkt: Union[bytes, Tuple[bytes]]) -> None:
        """ Send frame to ZMQ pub/sub socket """
        await (self._sock.send_multipart(pkt) if self._multipart else self._sock.send(pkt))

    def __repr__(self) -> str:
        return "ZMQPublisherEndpoint"



class Outgoing_AMQP_Endpoint:
    """
        Endpoint class to attach AMQP topics
    """
    type_identifier = "amqp-out"

    def __init__(self, m, exchange: str, routing_key: str):
        """
        Args:
            exchange:
            routing_key:
            kwargs: Additional keyword arguments will be added to as additional data
        """
        self.m = m
        self._exchange: str = exchange
        self._routing_key: str = routing_key

    async def send(self, pkt) -> None:
        """ Send packet to AMQP exchange """
        await self.m.channel.basic_publish(pkt, exchange=self._exchange, routing_key=self._routing_key)


class Incoming_AMQP_Endpoint:
    """
        Endpoint class to attach AMQP topics
    """
    type_identifier = "amqp-in"

    def __init__(self, m, exchange: str, routing_key: str):
        """
        """
        self.m = m
        self._exchange: str = exchange
        self._routing_key: str = routing_key
        self._queue_name: Optional[str] = None

    async def connect(self) -> None:
        """ Create new queue for incoming frames """
        declare_ok = await self.m.channel.queue_declare(exclusive=True)
        self._queue_name = declare_ok.queue
        await self.m.channel.basic_consume(declare_ok.queue, consumer_callback=self.receiver_callback, no_ack=True)
        await self.m.channel.queue_bind(declare_ok.queue, exchange=self._exchange, routing_key=self._routing_key)

    async def disconnect(self) -> None:
        """ """
        await self.m.channel.queue_delete(self._queue_name)
        self._queue_name = None

    async def receiver_callback(self, pkt: aiormq.types.DeliveredMessage) -> None:
        """ """
        self.m.route_frame(self, pkt.body)


class Outgoing_UDP_Endpoint:
    """
        UCP Endpoint for the packet router
    """
    type_identifier = "udp-out"
    def __init__(self, m, connect: str):
        self.m = m
        self._host, self._port = connect.split(":")
        self._port = int(self._port)
        self._sock: Optional[socket.socket] = None

    def connect(self) -> None:
        """ Create new UDP socket """
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def disconnect(self) -> None:
        """ Disconnect the UDP socket """
        self._sock = None

    async def send(self, pkt: bytes) -> None:
        """ """
        if not isinstance(pkt, bytes):
            raise ValueError(f"UDP can send only byte decoded packets! {type(pkt)} given")
        await self._sock.sendto(pkt, (self._host, self._port))


class Incoming_UDPEndpoint:
    """
        UDP Endpoint for the packet router
    """
    type_identifier = "udp-in"
    def __init__(self, m, bind: str):
        self.m = m
        self._host, self._port = bind.split(":")
        self._sock: Optional[socket.socket] = None

    def connect(self) -> None:
        """ Start listening UDP port """
        loop = asyncio.get_event_loop()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(self._host, self._port)
        loop.add_reader(self._sock, self._received_callback)

    async def disconnect(self) -> None:
        """ Disconnect the UDP socket """
        loop = asyncio.get_event_loop()
        loop.remove_reader(self._sock)
        self._sock.close()

    async def _received_callback(self) -> None:
        packet = await self._sock.recv()
        self.m.route_frame(self, packet)


class TCPEndpoint:
    """
    TCP Endpoint for the packet router
    """

    type_identifier = "tcp"

    def __init__(self,
            bind: Optional[str]=None,
            connect: Optional[str]=None
        ):
        """

        Args:
            bind:
            connect:
        """
        self._bind = bind
        self._connect = connect
        self._sock: Optional[socket.socket] = None
        self._listen_sock: Optional[socket.socket] = None
        self._closing: Optional[asyncio.Future] = None
        self._clients: List[socket.socket] = []

    async def connect(self):
        """ Make new TCP server/client """

        loop = asyncio.get_current_event_loop()
        if self._bind is not None:
            # Create new TCP socket and start listening new incoming connections
            host, port = self._bind.split(":")
            self._listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._listen_sock.setblocking(False)
            self._listen_sock.bind((host, int(port)))

            loop = asyncio.get_event_loop()
            loop.add_task(self._listen_task)
            self._closing = loop.create_future()

        elif self._connect is not None:
            # Create new TCP socket and connect to given address
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setblocking(False)
            await loop.sock_connect(self._sock, host, port = self._connect.split(":"))
            self._closing = loop.create_future()

        else:
            raise ValueError("Neither bind or connect!")

    async def _listen_task(self) -> None:
        """ Listen new incoming TCP connections """
        loop = asyncio.get_event_loop()
        while not self._closing.done():
            client, addr = await loop.sock_accept(self._listen_sock)
            print("New connection", addr)
            loop.add_task(self._receive_task(client))
        self._listen_sock.close()
        self._listen_sock = None

    async def _receive_task(self, client: socket.socket) -> None:
        """ Receive new frames from client """
        loop = asyncio.get_event_loop()
        self._clients.append(client)
        while not self._closing.done():
            pkt = await loop.sock_recv(client)
            self.m.route_frame(self, pkt)
        self._clients.remove(client)
        client.close()

    async def disconnect(self):
        """ Disconnect the TCP socket(s) """
        self._closing.set_result(0)

    async def send(self, pkt) -> None:
        """ Send frame to client(s) """
        if not isinstance(pkt, bytes):
            raise ValueError(f"TCP can send only byte decoded packets! {type(pkt)} given")
        if self._sock:
            self._sock.send(pkt)
        else:
            for client in self._clients:
                client.send(pkt)

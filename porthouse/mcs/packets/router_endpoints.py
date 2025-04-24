
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

    _closing: asyncio.Future
    _sock: zmq.Socket[bytes]

    def __init__(self,
            router,
            bind: Optional[str]=None,
            connect: Optional[str]=None,
            subscribe: str="",
            multipart: bool=False,
            **kwargs
        ):
        """
        Initalize ZMQ subscriber endpoint
        Args:
            router:
            bind: Address used for binding
            connect: Address used for connecting
            subcribe: Optional subscriber topic filter
            multipart: If true, the ZMQ multipart messages will be used.

        Remarks:
            If multipart is used, the received and transmitted packet objects are
            always tuples containing the bytes object. Formatter supporting this must be used!
        """
        self.router = router
        self._subscribe = subscribe
        self._bind = bind
        self._connect = connect
        self._multipart = multipart

    def connect(self) -> None:
        """ Create ZMQ socket, bind/connect it and subscribe """

        # Create socket and bind/connect it
        self._sock = self.router.zmq_ctx.socket(zmq.SUB)
        if self._connect is not None:
            self._sock.connect(self._connect)
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
        """ Disconnect the subscriber socket """
        print("ZMQ Subscriber disconnect")
        self._closing.set_result(0)
        self._sock.close()
        del self._sock

    async def _receiver(self) -> NoReturn:
        """ ZMQ receiver task  """
        try:
            while not self._closing.done():
                packet = await (self._sock.recv_multipart() if self._multipart else self._sock.recv())
                self.router.route_frame(self, packet)
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

    _closing: asyncio.Future
    _sock: zmq.Socket[bytes]

    def __init__(self,
            router,
            bind: Optional[str]=None,
            connect: Optional[str]=None,
            multipart: bool=False,
            **kwargs
        ):
        """
        """
        self.router = router
        self._bind = bind; self._connect = connect
        self._multipart = multipart

    def connect(self) -> None:
        """ Create ZMQ socket and bind/connect it """

        self._sock = self.router.zmq_ctx.socket(zmq.PUB)
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

    def __init__(self, router, exchange: str, routing_key: str, **kwargs):
        """
        Args:
            router:
            exchange:
            routing_key:
            kwargs: Additional keyword arguments will be added to as additional data
        """
        self.router = router
        self._exchange: str = exchange
        self._routing_key: str = routing_key

    async def send(self, pkt) -> None:
        """ Send packet to AMQP exchange """
        await self.router.channel.basic_publish(pkt, exchange=self._exchange, routing_key=self._routing_key)


class Incoming_AMQP_Endpoint:
    """
    Endpoint class to attach AMQP topics
    """
    type_identifier = "amqp-in"

    def __init__(self, router, exchange: str, routing_key: str, **kwargs):
        """
        """
        self.router = router
        self._exchange: str = exchange
        self._routing_key: str = routing_key
        self._queue_name: Optional[str] = None

    async def connect(self) -> None:
        """ Create new queue for incoming frames """
        declare_ok = await self.router.channel.queue_declare(exclusive=True)
        self._queue_name = declare_ok.queue
        await self.router.channel.basic_consume(declare_ok.queue, consumer_callback=self.receiver_callback, no_ack=True)
        await self.router.channel.queue_bind(declare_ok.queue, exchange=self._exchange, routing_key=self._routing_key)

    async def disconnect(self) -> None:
        """ """
        await self.router.channel.queue_delete(self._queue_name)
        self._queue_name = None

    async def receiver_callback(self, pkt: aiormq.abc.DeliveredMessage) -> None:
        """ """
        self.router.route_frame(self, pkt.body)


class Outgoing_UDP_Endpoint:
    """
    UDP Endpoint for the packet router
    """
    type_identifier = "udp-out"
    _sock: socket.socket

    def __init__(self, router, connect: str, **kwargs):
        """
        """
        self.router = router
        self._host, self._port = connect.split(":")
        self._port = int(self._port)

    def connect(self) -> None:
        """ Create new UDP socket """
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def disconnect(self) -> None:
        """ Disconnect the UDP socket """
        if self._sock:
            self._sock.close()
            del self._sock

    async def send(self, pkt: bytes) -> None:
        """ """
        if not isinstance(pkt, bytes):
            raise ValueError(f"UDP can send only byte decoded packets! {type(pkt)} given")
        self._sock.sendto(pkt, (self._host, self._port))


class Incoming_UDPEndpoint:
    """
    UDP Endpoint for the packet router
    """
    type_identifier = "udp-in"
    _sock: socket.socket

    def __init__(self, router, bind: str, **kwargs):
        self.router = router
        self._host, self._port = bind.split(":")

    def connect(self) -> None:
        """ Start listening UDP port """
        loop = asyncio.get_event_loop()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((self._host, self._port))
        loop.add_reader(self._sock, self._received_callback)

    async def disconnect(self) -> None:
        """ Disconnect the UDP socket """
        loop = asyncio.get_event_loop()
        loop.remove_reader(self._sock)
        self._sock.close()

    async def _received_callback(self) -> None:
        packet: bytes = self._sock.recv(1024, socket.SOCK_NONBLOCK)
        self.router.route_frame(self, packet)


class TCPEndpoint:
    """
    TCP Endpoint for the packet router
    """

    type_identifier = "tcp"

    _sock: socket.socket
    _listen_sock: socket.socket
    _closing: asyncio.Future

    def __init__(self,
            router,
            bind: Optional[str]=None,
            connect: Optional[str]=None,
            **kwargs
        ):
        """

        Args:
            router:
            bind:
            connect:
        """
        self._bind = bind
        self._connect = connect
        self._clients: List[socket.socket] = []

    async def connect(self):
        """ Make new TCP server/client """

        loop = asyncio.get_running_loop()
        if self._bind is not None:
            # Create new TCP socket and start listening new incoming connections
            host, port = self._bind.split(":")
            self._listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._listen_sock.setblocking(False)
            self._listen_sock.bind((host, int(port)))

            loop = asyncio.get_event_loop()
            loop.create_task(self._listen_task())
            self._closing = loop.create_future()

        elif self._connect is not None:
            # Create new TCP socket and connect to given address
            host, port = self._connect.split(":")
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setblocking(False)
            await loop.sock_connect(self._sock, (host, int(port)))
            self._closing = loop.create_future()

        else:
            raise ValueError("Neither bind or connect!")

    async def _listen_task(self) -> None:
        """ Listen new incoming TCP connections """
        loop = asyncio.get_event_loop()
        while not self._closing.done():
            client, addr = await loop.sock_accept(self._listen_sock)
            print("New connection", addr)
            loop.create_task(self._receive_task(client))
        self._listen_sock.close()
        del self._listen_sock

    async def _receive_task(self, client: socket.socket) -> None:
        """ Receive new frames from client """
        loop = asyncio.get_event_loop()
        self._clients.append(client)
        while not self._closing.done():
            pkt = loop.sock_recv(client, 1024)
            self.router.route_frame(self, pkt)
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

"""
BaseModule is the base class for all the mission control software modules.
"""

from os.path import join as path_join
import asyncio
from concurrent.futures import TimeoutError as AsyncIOTimeoutError
import json
import uuid
import datetime
import logging
import logging.handlers
from typing import Optional, Union
from .config import load_globals
import aiormq
import aiormq.abc

from .log.amqp_handler_async import AMQPLogHandler


# Define what is being imported by default
__all__ = [
    "BaseModule",
    "RPCError",
    "RPCRequestError",
    "RPCRequestTimeout",
    "queue",
    "bind",
    "rpc"
]

# Global dicts for automatic AMQP queues and exchange bindings
#global amqp_queues, amqp_binds
amqp_queues, amqp_binds = {}, {}


class RPCError(Exception):
    """
        Executed RPC command failed.
    """

class RPCRequestError(Exception):
    """
        Executing remote RPC failed
    """

class RPCRequestTimeout(Exception):
    """
        Executing remote RPC timed out
    """


def json_formatter(obj):
    """
        Formatter function for json.dumps
    """
    if isinstance(obj, datetime.datetime):
        #return obj.timestamp()
        return obj.isoformat()
    return obj


class BaseModule:
    """
        The BaseModule
    """

    def __init__(self,
                 amqp_url: str,
                 prefix: str = None,
                 log_path: str = "/tmp/",
                 module_name: str = None,
                 autocreate: bool = True,
                 debug: bool = False,
                 **kwarg):
        """
        Initialize the Module.
        Create logs, connect to AMQP, autocreate queues etc.

        Args:
            amqp_url: AMQP server URL (amqp://guest:guest@localhost:5672/)
            prefix: Routing key prefix used for incoming and outgoing messages.
            log_path: Directory for log files
            module_name: Name of the module used.
                If not defined the used name is same as the name of the class.
            autocreate: If true
            debug: If true additional debug features, such as log debug prints, are turned on.
            kwargs: Extra configurations
        """

        self.debug = debug
        self.prefix = prefix
        self.autocreate = autocreate
        self.log = None
        self.log_path = log_path
        self.module_name = module_name

        # State variables for RPC calls
        self.rpc_futures = {}
        self.rpc_response_queue = None

        # Run async connection before returning
        if amqp_url is None:
            amqp_url = load_globals()["amqp_url"]
        asyncio.get_event_loop().run_until_complete(self.__connect(amqp_url))

        #asyncio.get_event_loop().create_task(self.heartbeat_task(10))


    def run(self):
        """
        Start the async loop
        """
        loop = asyncio.get_event_loop()
        loop.run_forever()


    async def __connect(self, amqp_url):
        """
        AMQP connection coroutine. Called automatically by the __init__.

        Args:
            amqp_url: AMQP server URL
        """

        # Init AMQP
        self.connection = await aiormq.connect(amqp_url)
        self.channel = await self.connection.channel()

        # Init logging
        if self.module_name is None:
            self.module_name = str(self.__class__.__name__)
        self.create_log_handlers(self.log_path, self.module_name)

        if self.autocreate:
            await self.__autocreate_queues()

        # Init done
        self.log.info("Module  %r started!", self.module_name)


    async def heartbeat_task(self, interval):
        """
            Heartbeat task transmits
        """
        while True:
            await self.publish("heartbeat", bool(self.module_name))
            await asyncio.sleep(interval)

    async def __autocreate_queues(self):
        """
            Autocreate queues and bindings according to the decorator bindings.
        """

        classname = self.__class__.__name__
        if classname not in amqp_queues:
            return

        # Autocreate queues
        for callback, queue_name in amqp_queues[classname].items():

            # Resolve callback function
            callback_func = getattr(self, callback.rsplit(".", 1)[1])
            assert(callable(callback_func))

            # Create queue
            inbox = await self.channel.queue_declare(queue_name, exclusive=True, auto_delete=True, durable=False)
            #await self.channel.basic_qos(prefetch_count=1, prefetch_size=0, connection_global=False)

            await self.channel.basic_consume(inbox.queue, consumer_callback=callback_func, no_ack=True)


            # Auto binding for the queue
            if callback in amqp_binds:
                for exchange, routing_key, kwargs in amqp_binds[callback]:
                    if kwargs.get("prefixed", False):
                        routing_key = self.prefixed(routing_key)
                    await self.channel.queue_bind(inbox.queue, exchange=exchange, routing_key=routing_key)


    def prefixed(self, routing_key: str = "") -> str:
        """
        Return prefixed version of give routing_key.
        """
        return "%s.%s" % (self.prefix, routing_key) if self.prefix else routing_key


    async def publish(self, msg, prefixed: bool = False, **kwargs) -> None:
        """
        Publish a message to AMQP exchange

        Args:
            msg: Message to be send.
            prefixed: Is the routing_key prefixed
            kwargs: should include routing_key and exchange.
        """
        if prefixed and self.prefix:
            kwargs["routing_key"] = "%s.%s" % (self.prefix, kwargs["routing_key"])

        if isinstance(msg, dict):
            msg = json.dumps(msg, default=json_formatter).encode("ascii")

        await self.channel.basic_publish(msg, **kwargs)


    def create_log_handlers(self, log_path: str, module_name: str):
        """
        Create AMQP and file (+ stdout) log handlers for logging

        Args:
            log_path:    Directory for log file
            module_name: Name used to identify module
        """

        self.log = logging.getLogger(module_name)
        self.log.setLevel(logging.INFO)

        # AMQP log handler
        amqp_handler = AMQPLogHandler(module_name, self.channel)
        amqp_handler.setLevel(logging.INFO)
        self.log.addHandler(amqp_handler)

        # File log handler
        log_file = path_join(log_path, module_name + ".log")
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=int(2e6), backupCount=5)
        file_handler.setFormatter(formatter)
        self.log.addHandler(file_handler)

        if True or self.debug:
            # Create stdout log handler
            stdout_handler = logging.StreamHandler()
            stdout_handler.setFormatter(formatter)
            self.log.addHandler(stdout_handler)

        if self.debug:
            self.log.setLevel(logging.DEBUG)


    def task_done_handler(self, task: asyncio.Task, cancelled_msg: Union[str, bool, None] = None):
        """
        Handle task done callback
        """
        try:
            task.result()
        except asyncio.CancelledError:
            if cancelled_msg:
                self.log.warning(f"Task {task.get_name()} cancelled" if cancelled_msg is True else cancelled_msg)
        except Exception:
            self.log.error(f"Task {task.get_name()} failed:", exc_info=True)


    async def send_rpc_response(self, request: aiormq.abc.DeliveredMessage, data: dict):
        """
        Helper function to send a response to incoming RPC query.

        If RPC decorator is used the callback function should return the response
        dict instead of calling this method. This method is called by the
        decorator.

        Args:
            request: Original RPC request message object.
            data: Data to be returned to caller.
        """

        # If there's no reply_to field, no answer can be sent
        if "reply_to" not in request.header.properties:
            raise RuntimeError("RPC request missing the 'reply_to' -field")

        if isinstance(data, (dict, list)):
            data = json.dumps(data)

        # Send response and ACK
        await self.channel.basic_publish(
            data.encode(),
            routing_key=request.header.properties.reply_to,
            properties=aiormq.spec.Basic.Properties(
                content_type='text/plain',
                correlation_id=request.header.properties.correlation_id
            )
        )

        # TODO: aiormq close the channel for some reason if an ack is sent!
        #await request.channel.basic_ack(request.delivery.delivery_tag)


    async def __rpc_response(self, message: aiormq.abc.DeliveredMessage):

        """
        Callback function to handle received reponse for an outgoing RPC request.
        Called by the AMQP library.
        """

        corr_id = message.header.properties.correlation_id
        if corr_id in self.rpc_futures:
            future = self.rpc_futures.pop(corr_id)
            future.set_result(message.body)
        else:
            raise RuntimeError(
                "Unknown correlation_id on RPC response queue! Possibly a late RPC response.")


    async def send_rpc_request(self, exchange: str, routing_key: str, query_data: Optional[dict] = None, timeout: float = 1):
        """
        Send a RPC query to remote process and wait for response.

        Args:
            exchange: Name of the exchange where the RPC request is sent to.
            routing_key: Routing key for the RPC request
            query_data: Data to be included to RPC request
            timeout: Requets timeout time in seconds
        """

        # Create RPC response queue if it doesn't exist yet
        if not self.rpc_response_queue:
            declare_ok = await self.channel.queue_declare(exclusive=True, auto_delete=True)
            self.rpc_response_queue = declare_ok.queue
            await self.channel.basic_consume(self.rpc_response_queue, self.__rpc_response)

        if query_data is None:
            query_data = {}

        # JSON format the data
        if isinstance(query_data, (dict, list)):
            query_data = json.dumps(query_data)

        try:
            # Create future for the RPC response
            future = asyncio.get_event_loop().create_future()
            corr_id = str(uuid.uuid4())
            self.rpc_futures[corr_id] = future

            # Send the RPC call
            await self.channel.basic_publish(
                query_data.encode(),
                exchange=exchange,
                routing_key=routing_key,
                properties=aiormq.spec.Basic.Properties(
                    content_type='text/plain',
                    correlation_id=corr_id,
                    reply_to=self.rpc_response_queue,
                )
            )

        except aiormq.exceptions.ChannelNotFoundEntity as exc:
            raise RPCRequestError("Exchange not found!") from exc

        try:
            # Wait until the future is fulfilled
            res = await asyncio.wait_for(future, timeout=timeout)
            res = json.loads(res)

            if "error" in res:
                raise RPCRequestError(res["error"])
            return res

        except ValueError as exc:
            raise RPCRequestError("Failed to parse JSON RPC response!") from exc

        except AsyncIOTimeoutError as exc:
            raise RPCRequestTimeout() from exc

        finally:
            # Remove future if not fulfilled
            if corr_id in self.rpc_futures:
                del self.rpc_futures[corr_id]


def queue(queue_name=""):
    """
    Queue decorator for automatic queue creating.

    Remarks:
        See examples about how to use the queue and bind decorators.

    Args:
        queue_name: Optional queue name
    """

    def decorator(callback):
        classname = callback.__qualname__.rsplit(".", 1)[0]
        if classname not in amqp_queues:
            amqp_queues[classname] = {}
        amqp_queues[classname][callback.__qualname__] = queue_name
        return callback

    return decorator


def bind(exchange: str, routing_key: str, **kwargs):
    """
    Bind decorator for automatic queue binding.

    Remarks:
        See examples about how to use the queue and bind decorators.

    params:
        exchange: Name of the exchange to be binded
        routing_key: Routing key for filtering subscribed messages
        kwargs: Optional keyword arguments
            - prefixed: Is the routing_key prefixed
    """

    def decorator(callback):
        funcname = callback.__qualname__
        if funcname not in amqp_binds:
            amqp_binds[funcname] = []
        amqp_binds[funcname].append((exchange, routing_key, kwargs))
        return callback
    return decorator


def rpc():
    """
    RPC decorator to autocreate RPC queue and callback.

    Remarks:
        See examples about how to use the RPC decorator.
    """

    def decorator(callback):

        # Add callback to autoqueue list
        classname = callback.__qualname__.rsplit(".", 1)[0]
        if classname not in amqp_queues:
            amqp_queues[classname] = {}
        amqp_queues[classname][callback.__qualname__] = ""

        # When the a message is received call the callback function via __rpc_parser
        def __rpc_wrapper(self, msg):
            return __rpc_parser(self, callback, msg)
        return __rpc_wrapper

    return decorator


async def __rpc_parser(self, callback, request):
    """
    Helper function used to parse incoming RPC request.
    """

    try:

        # Try to parse JSON payload
        try:
            request_data = json.loads(request.body)
        except (ValueError, TypeError) as exc:
            raise RPCError("Error while parsing json message:\n%s\n%s"
                % (request.body, exc.args[0])
            ) from exc

        request_name = request.delivery['routing_key']

        # Remove prefix from the rounting_key
        if self.prefix and request_name.startswith(self.prefix):
            request_name = request_name[len(self.prefix)+1:]

        ret = callback(self, request_name, request_data)
        if asyncio.iscoroutine(ret):
            ret = await ret
        if ret is None:
            ret = {}

        await BaseModule.send_rpc_response(self, request, ret)

    except RPCError as exc:
        self.log.error("RPCError: %s failed: %s",
            request.delivery['routing_key'], exc, exc_info=True)
        await BaseModule.send_rpc_response(self, request, {
            "error": "RPC Error: %s" % exc
        })

    except Exception as exc:
        self.log.error("RPC %s failed: Unhandled exception %r",
            request.delivery['routing_key'], exc, exc_info=True)
        await BaseModule.send_rpc_response(self, request, {
            "error": "Unhandled exception %r" % exc
        })

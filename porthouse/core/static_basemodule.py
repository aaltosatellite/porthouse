from os import environ
from os.path import join as path_join
import json
import uuid
import time
import socket
import logging
import logging.handlers
import datetime
from .basemodule_async import amqp_binds, amqp_queues
#import basemodule_async as BMA
import amqp
from .log.amqp_handler import AMQPLogHandler
from urllib.parse import urlparse

# Define what is being imported by default
__all__ = [
    "BaseModule",
    "Message",
    "RPCError",
    "RPCRequestError",
    "RPCRequestTimeout",
    "queue",
    "bind",
    "rpc"
]

# Global dicts for automatic AMQP queues and exchange bindings
#global amqp_queues, amqp_binds
# amqp_queues, amqp_binds

Message = amqp.basic_message.Message


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



def json_formatter(o):
    """
        Formatter function for json.dumps
    """
    if isinstance(o, datetime.datetime):
        return float(o.strftime("%s"))


class BaseModule:
    """

    """
    log = None
    def __init__(self,amqp_url, prefix=None, log_path="/tmp/", module_name=None, autocreate=True, debug=False, **kwargs):
        self.debug = debug
        self.prefix = prefix
        self.timeouts = list()
        self.queues = dict()
        self.responses = dict()
        self.rpc_response_queue = None

        # Init AMQP
        amqp_url = urlparse(amqp_url or environ.get('MCC_AMQP_ACCESS'))
        self.connection = amqp.Connection(host=amqp_url.hostname,
            userid=amqp_url.username, password=amqp_url.password)
        self.connection.connect()
        self.channel = self.connection.channel()

        # Init logging
        if not module_name:
            module_name = str(self.__class__.__name__)

        self.create_log_handlers(log_path, module_name)

        if autocreate:
            self.autocreate_queues()

        # Init done
        self.log.info("Module \"%s\" started!", module_name)

    def autocreate_queues(self):
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

            # Create queue
            inbox = self.channel.queue_declare(queue_name, exclusive=True)
            self.channel.basic_consume(
                queue=inbox.queue, callback=callback_func)
            self.queues[callback] = inbox

            # Auto binding for the queue
            if callback in amqp_binds:
                for exchange, routing_key, kwargs in amqp_binds[callback]:
                    if kwargs.get("prefixed", False):
                        routing_key = self.prefixed(routing_key)
                    self.channel.queue_bind(
                        queue=inbox.queue, exchange=exchange, routing_key=routing_key)

    def prefixed(self, routing_key=""):
        """
            Return prefixed version of give routing_key
        """
        return "%s.%s" % (self.prefix, routing_key) if self.prefix else routing_key

    def publish(self, msg, prefixed=False, **kwarg):
        """
            Basic publish
        """
        if prefixed and self.prefix:
            kwarg["routing_key"] = "%s.%s" % (
                self.prefix, kwarg["routing_key"])
        if isinstance(msg, dict):
            msg = amqp.basic_message.Message(json.dumps(msg, default=json_formatter))
        self.channel.basic_publish(msg, **kwarg)

    def create_log_handlers(self, log_path, module_name):
        """
            Create AMQP and file (+ stdout) log handlers for logging

            params:
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
            # Change general logging level
            self.log.setLevel(logging.DEBUG)

    def run(self):
        """
            Run forever listening AMQP messages
        """

        try:
            while True:
                try:
                    self.connection.drain_events(timeout=0.25)
                # except (BrokenPipeError, AttributeError):
                #    # A possible AMQP's crash exception when the process is killed with Ctrl+C
                #    break
                except socket.timeout:
                    pass
                self.check_timeouts()
        except KeyboardInterrupt:
            pass
        finally:
            self.connection.close()

    def clear_timeouts(self):
        self.timeouts = []

    def check_timeouts(self):
        for timeout in self.timeouts:
            if timeout[0] < time.time():
                try:
                    timeout[1]()
                    self.timeouts.remove(timeout)
                except ValueError:
                    pass

    def add_timeout(self, deadline, callback):
        # DON'T USE ME PLZ!
        self.timeouts.append((time.time() + deadline, callback))

    def send_rpc_response(self, request, data):
        """
            Send RPC response to the original sender
        """

        # If there's no reply_to field, no answer can be sent
        if "reply_to" not in request.properties:
            return

        if isinstance(data, (dict, list)):
            data = json.dumps(data)

        # Send response
        msg = Message(body=data)
        if "correlation_id" in request.properties:
            msg.properties["correlation_id"] = request.properties["correlation_id"]

        self.channel.basic_publish(
            msg, routing_key=request.properties["reply_to"])
        self.channel.basic_ack(request.delivery_tag)

    def __rpc_response(self, msg):
        """
            Handle RPC response; AMQP callback
        """
        self.responses[msg.properties["correlation_id"]] = msg

    def send_rpc_request(self, exchange, routing_key, query_data=None, timeout=1):
        """
            Send a RPC query
        """
        if query_data is None:
            query_data = dict()
        # Create RPC response queue if it doesn't exist yet
        if not self.rpc_response_queue:
            self.rpc_response_queue = self.channel.queue_declare(
                exclusive=True)
            self.channel.basic_consume(
                queue=self.rpc_response_queue.queue, callback=self.__rpc_response)

        # JSON dumps!
        if isinstance(query_data, list) or isinstance(query_data, dict):
            query_data = json.dumps(query_data)

        corr_id = str(uuid.uuid4())

        try:
            # Send RPC call
            msg = Message(query_data)
            msg.properties["correlation_id"] = corr_id
            msg.properties["reply_to"] = self.rpc_response_queue.queue
            self.channel.basic_publish(
                msg, exchange=exchange, routing_key=routing_key)

            # Wait for response
            end = time.time() + timeout
            while corr_id not in self.responses and end > time.time():
                try:
                    timeout_left = max(0, int(end - time.time()))
                    self.connection.drain_events(timeout=timeout_left)
                except socket.timeout:
                    pass

        except amqp.exceptions.NotFound:
            raise RPCRequestError("Exchange not found!")

        # Check received response
        if corr_id in self.responses:
            try:
                # Parse response
                res = json.loads(self.responses[corr_id].body)
                # Remove reponse from the map before exiting
                del self.responses[corr_id]

                if "error" in res:
                    raise RPCRequestError(res["error"])
                return res

            except ValueError:
                raise RPCRequestError("Failed to parse JSON RPC response!")

        raise RPCRequestTimeout()


def queue(queue_str=""):
    """
        Queue decorator to autocreate queue and callback
    """
    def decorator(callback):
        classname = callback.__qualname__.rsplit(".", 1)[0]
        if classname not in amqp_queues:
            amqp_queues[classname] = {}
        amqp_queues[classname][callback.__qualname__] = queue_str
        return callback
    return decorator


def bind(exchange, routing_key, **kwargs):
    """
        Bind decorator to autobind queue to exchange.
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
        RPC decorator to autocreate RPC queue and callback
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


def __rpc_parser(self, callback, request):
    """
        Do extra parsing and error handling for RPC calls
    """
    try:
        try:
            request_data = json.loads(request.body)
        except (ValueError, TypeError) as e:
            raise RPCError("Error while parsing json message:\n%s\n%s" %
                           (request.body, e.args[0]))

        request_name = request.delivery_info['routing_key']

        # Remove prefix from the rounting_key
        if self.prefix and request_name.startswith(self.prefix):
            request_name = request_name[len(self.prefix)+1:]

        ret = callback(self, request_name, request_data) or {}

        BaseModule.send_rpc_response(self, request, ret)

    except RPCError as e:
        self.log.error("RPCError: %s failed: %s",
                       request.delivery_info['routing_key'], e, exc_info=True)
        BaseModule.send_rpc_response(
            self, request, {"error": "RPC Error: %s" % e})

    except Exception as e:
        self.log.error("RPC %s failed: Unhandled exception %r",
                       request.delivery_info['routing_key'], e, exc_info=True)
        BaseModule.send_rpc_response(
            self, request, {"error": "Unhandled exception %r" % e})

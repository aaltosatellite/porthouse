"""
    Utility functions for creating RPC requests.
"""

import time
import json
import uuid
import socket
from os import environ
from urllib.parse import urlparse
from typing import Tuple, Optional, Dict, Any

import amqp

from .config import load_globals
from .static_basemodule import RPCRequestError, RPCRequestTimeout



connection = None
channel = None
rpc_responses = { }
rpc_response_queue = None


def amqp_connect(
        amqp_url: Optional[str]
    ) -> Tuple[amqp.Connection, amqp.Channel]:
    """
    Connect to AMQP message broker.

    Args:
        amqp_url: Connection URL for the AMQP message broker.

    Returns:
        AMQP connection and channel objects.
    """
    if amqp_url is None:
        amqp_url = load_globals()["amqp_url"]

    global connection, channel
    amqp_url = urlparse(amqp_url)
    connection = amqp.Connection(host=amqp_url.hostname, userid=amqp_url.username, password=amqp_url.password)
    connection.connect()
    channel = connection.channel()
    return connection, channel



def __rpc_response(
        message: amqp.basic_message.Message
    ) -> None:
    """
    Callback function to handle received reponse for an outgoing RPC request.

    Remarks:
        Called by the AMQP library.
    """
    global rpc_response

    corr_id = message.properties["correlation_id"]
    rpc_responses[corr_id] = message.body


def send_rpc_request(
        exchange: str,
        routing_key: str,
        args: Optional[dict] = None,
        timeout: Optional[float] = 1
    ) -> Dict[str, Any]:
    """
    Send a RPC query to remote process and wait for response.

    Args:
        exchange: Name of the exchange where the RPC request is sent to.
        routing_key: Routing key for the RPC request
        query_data: Data to be included to RPC request
        timeout: Requets timeout time in seconds

    Returns:
        RPC response data as a dict.

    Raises:
        RPCRequestError, RPCRequestTimeout
    """
    global channel, rpc_futures, rpc_response_queue

    # Create RPC response queue if it doesn't exist yet
    if not rpc_response_queue:
        declare_ok = channel.queue_declare(exclusive=True, auto_delete=True)
        rpc_response_queue = declare_ok.queue
        channel.basic_consume(queue=rpc_response_queue, callback=__rpc_response)


    if args is None:
        args = {}

    # JSON format the data
    if isinstance(args, (dict, list)):
        args = json.dumps(args)

    corr_id = str(uuid.uuid4())

    try:
        # Send RPC call
        msg = amqp.basic_message.Message(args)
        msg.properties["correlation_id"] = corr_id
        msg.properties["reply_to"] = rpc_response_queue
        channel.basic_publish(msg, exchange=exchange, routing_key=routing_key)

        # Wait for response
        end = time.time() + timeout
        while corr_id not in rpc_responses and end > time.time():
            try:
                timeout_left = max(0, end - time.time())
                connection.drain_events(timeout=timeout_left)
            except socket.timeout:
                pass

    except amqp.exceptions.NotFound:
        raise RPCRequestError("Exchange not found!")

    # Check received response
    if corr_id in rpc_responses:
        try:
            # Parse response
            res = json.loads(rpc_responses[corr_id])
            # Remove reponse from the map before exiting
            del rpc_responses[corr_id]

            if "error" in res:
                raise RPCRequestError(res["error"])
            return res

        except ValueError:
            raise RPCRequestError("Failed to parse JSON RPC response!")

    raise RPCRequestTimeout()

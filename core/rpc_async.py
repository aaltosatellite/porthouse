"""
    Utility functions for creating RPC requests.
"""

import json
import uuid
import asyncio
from os import environ
from concurrent.futures import TimeoutError as AsyncIOTimeoutError
from typing import Tuple, Optional, Dict, Any

import aiormq
import aiormq.abc

from .config import load_globals
from .basemodule_async import RPCRequestError, RPCRequestTimeout

connection = None
channel = None
rpc_futures = {}
rpc_response_queue = None


async def amqp_connect(
        amqp_url: Optional[str] = None
    ) -> Tuple[aiormq.Connection, aiormq.Channel]:
    """
    Connect to AMQP message broker.

    Args:
        amqp_url: Connection URL for the AMQP message broker.

    Returns:
        AMQP connection and channel objects.
    """
    global connection, channel

    if amqp_url is None:
        amqp_url = load_globals()["amqp_url"]

    connection = await aiormq.connect(amqp_url)
    channel = await connection.channel()
    return connection, channel

def __rpc_response(
        message: aiormq.abc.DeliveredMessage
    ) -> None:
    """
    Callback function to handle received reponse for an outgoing RPC request.

    Remarks:
        Called by the AMQP library.
    """
    global rpc_futures

    corr_id = message.header.properties.correlation_id
    if corr_id in rpc_futures:
        future = rpc_futures.pop(corr_id)
        future.set_result(message.body)
    else:
        raise RuntimeError(
            "Unknown correlation_id on RPC response queue!" \
            "Possibly a late RPC response.")


async def send_rpc_request(
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
        declare_ok = await channel.queue_declare(exclusive=True, auto_delete=True)
        rpc_response_queue = declare_ok.queue
        await channel.basic_consume(rpc_response_queue, __rpc_response)

    if args is None:
        args = {}

    # JSON format the data
    if isinstance(args, (dict, list)):
        args = json.dumps(args)

    try:
        # Create future for the RPC response
        future = asyncio.get_event_loop().create_future()
        corr_id = str(uuid.uuid4())
        rpc_futures[corr_id] = future

        # Send the RPC call
        await channel.basic_publish(
            args.encode(),
            exchange=exchange,
            routing_key=routing_key,
            properties=aiormq.spec.Basic.Properties(
                content_type='text/plain',
                correlation_id=corr_id,
                reply_to=rpc_response_queue,
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

    except (AsyncIOTimeoutError, asyncio.exceptions.TimeoutError) as exc:
        raise RPCRequestTimeout() from exc

    finally:
        # Remove future if not fulfilled
        if corr_id in rpc_futures:
            del rpc_futures[corr_id]

import asyncio
import json
from typing import Set, Dict, List

import aiormq
import websockets

from porthouse.core.basemodule_async import BaseModule, queue, bind

from .utils import WebRPCError

from .services.system import SystemService
from .services.tracking import TrackingService
from .services.events import EventsService
from .services.housekeeping import HousekeepingService


class OpenMCTProtocol(websockets.WebSocketServerProtocol):
    """
    Inherited protocol handler class which contains per connection informatation
    such as subscribed telemetry channels etc.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.subscriptions: Dict[str, List[str]] = { }

    @property
    def name(self) -> str:
        """
        Return a name for the client. Used for debugging purposes.
        """
        return "%s:%d" % self.transport.get_extra_info('peername')

    async def send_json(self, **kwargs) -> None:
        """
        Send JSON formatted packet to web browser.
        """
        await self.send(json.dumps(kwargs))



class OpenMCTBackend(BaseModule):
    """
    Module to implement OpenMCT backend
    """

    def __init__(self, ws_host: str, ws_port: int, hk_schema: str, db_url: str, **kwargs):
        """
        Initialize OpenMCT backend module.

        Args:
            ws_host: WebSocket listening address (127.0.0.1 or 0.0.0.0)
            ws_port: WebSocket listening port
            hk_schema: Housekeeping schema filepath
        """
        BaseModule.__init__(self, **kwargs)
        self.clients: Set[OpenMCTProtocol] = set()

        self.services = {
            "housekeeping": HousekeepingService(self, db_url, "fs1p", hk_schema),
            "system": SystemService(self),
            "events": EventsService(self),
            "tracking": TrackingService(self)
        }

        # Create websocket server
        start_server = websockets.serve(
            ws_handler=self.ws_socket_handler,
            host=ws_host,
            port=ws_port,
            create_protocol=OpenMCTProtocol,
            ping_interval=1
        )

        asyncio.get_event_loop().run_until_complete(start_server)


    async def ws_socket_handler(self, client: OpenMCTProtocol, path: str) -> None:
        """
        Websocket connection handling coroutine.
        This coroutine is called by the websockets protocol implementation.

        Args:
            client: Client protocol object
            path: URL path used to open the connection
        """

        self.clients.add(client)
        self.log.debug("New connection from %s", client.name)

        try:
            async for data in client:

                try:
                    message = json.loads(data)
                    self.log.debug("New command: %r", message)
                    print(message)
                    service = message.get("service", None)
                    if service not in self.services:
                        raise WebRPCError(f"No such service {service!r}")

                    if "method" not in message:
                        raise WebRPCError("Missing 'method' field")

                    res = self.services[service].rpc_command(client,
                        method=message["method"],
                        params=message.get("params", None))

                    if asyncio.iscoroutine(res):
                        res = await res

                    await client.send_json(result=res, id=message.get("id", None))

                except json.decoder.JSONDecodeError:
                    self.log.error("Malformed JSON: %r", data)
                    continue

                except websockets.exceptions.ConnectionClosedError:
                    raise

                except KeyError as exc:
                    self.log.warning("Missing arg", exc_info=True)
                    await client.send_json(error={
                        "code": -1,
                        "message": str(exc)
                    }, id=message.get("id", None))

                except WebRPCError as exc:
                    self.log.warning("WebRPCError", exc_info=True)
                    await client.send_json(error={
                        "code": -1,
                        "message": str(exc)
                    }, id=message.get("id", None))

                except Exception as exc:
                    self.log.warning("Error while handing WebSocket command", exc_info=True)
                    await client.send_json(error={
                        "code": -500,
                        "message": repr(exc)
                    }, id=message.get("id", None))

        except websockets.exceptions.ConnectionClosedError:
            pass

        finally:
            self.clients.remove(client)
            self.log.debug("Client %s disconnected!", client.name)



    @queue()
    @bind(exchange="events", routing_key="fs1.update")
    @bind(exchange="log", routing_key="*")
    @bind(exchange="housekeeping", routing_key="fs1.update")
    async def handle_message(self, msg: aiormq.types.DeliveredMessage) -> None:
        """
        Handle message from the AMQP

        Args:
            msg: AMQP message object
        """

        try:
            message = json.loads(msg.body)
        except:
            self.log.debug("Invalid JSON", exc_info=True)
            return

        self.log.debug("event: %s, %s", msg.delivery.exchange, msg.delivery.routing_key)

        ret = None
        exchange = msg.delivery.exchange

        if exchange == "events":
            ret = self.services["events"].handle_subscription(message)
        elif exchange == "logs":
            ret = self.services["system"].handle_subscription(message)
        elif exchange  == "housekeeping":
            ret = self.services["housekeeping"].handle_subscription(message)

        if asyncio.iscoroutine(ret):
            await ret


if __name__ == "__main__":
    OpenMCTBackend( \
        ws_host="127.0.0.1",
        ws_port=8888,
        hk_schema="../foresail/housekeeping.json",
        db_url="postgres://mcs:PASSWORD@localhost/foresail",
        amqp_url="amqp://guest:guest@localhost:5672/",
        debug=True
    ).run()

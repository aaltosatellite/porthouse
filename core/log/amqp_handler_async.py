"""
    This module implements AMQP logging handler which can be used with expression as target:
    pass the Python's standard logging system. The logging handler publishes all incoming log
    entries to common AMQP log exchange.
"""

import json
import logging
import asyncio
import aiormq

# TODO: aiologger should be used with asyncio instead of standard logging-module

class AMQPLogHandler(logging.Handler):
    """
    AMQP Log Handler class
    """

    def __init__(self,
            module: str,
            channel: aiormq.channel.Channel):
        """
        Initialize asynchronous AMQP log handler.

        Args:
            module: Name of the module which is outputting logging
            channel: aiormq channel object used to publish log entries
        """
        logging.Handler.__init__(self)

        self.module = module
        self.channel = channel


    def emit(self, record):
        """
        Send the log message to the broadcast queue.

        Remarks:
            This functions is requred to be compatible with Python logging system's emit call.

        Args:
            record: Log record object
        """

        # If amqp connection has been closed
        if not self.channel or self.channel.is_closed or not self.channel.connection:
            return

        try:
            msg = json.dumps({
                "module": self.module,
                "level": record.levelname.lower(),
                "created": record.created,
                "message": (record.msg % record.args if record.args else record.msg),
            }).encode("ascii")

            # TODO: The ugly part!
            asyncio.get_event_loop().create_task(
                self.channel.basic_publish(msg, exchange='log', routing_key=record.levelname.lower()))
        except Exception as e:
            raise Exception("Error %s in AMQPLogHandler, msg: %s, args: %s" % (e, record.msg, record.args)) from e


if __name__ == "__main__":
    """
        Testing...
    """

    async def main():

        # Perform connection
        connection = await aiormq.connect("amqp://guest:guest@localhost/")

        # Creating a channel
        channel = await connection.channel()

        # Create logger with the AMQP handler
        logger = logging.getLogger("mcc")
        logger.setLevel(logging.DEBUG)
        handler_messages = AMQPLogHandler("test", channel)
        logger.addHandler(handler_messages)

        # Announce messages
        logger.info("Wou! Life is amaizing")
        logger.warning("Wait! What! Something is wrong....")
        logger.error("Ouch! This must hurt!")
        logger.critical("Nooo! No I'm dying!")

        # Wait a bit before dying because the publish calls are not waiting
        await asyncio.sleep(0.5)

    asyncio.run(main())

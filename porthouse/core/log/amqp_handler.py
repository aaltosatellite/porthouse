"""
    This module implements AMQP logging handler which can be used with expression as target:
    pass the Python's standard logging system. The logging handler publishes all incoming log
    entries to common AMQP log exchange.
"""

import logging
import json
import amqp

class AMQPLogHandler(logging.Handler):
    def __init__(self,
            module: str,
            channel):
        """
            Initz
        """
        logging.Handler.__init__(self)

        self.module = module
        self.channel = channel


    def emit(self, record):
        """
            Send the log message to the broadcast queue
        """

        # If amqp connection has been closed
        if not self.channel or not self.channel.connection:
            return

        message = {
            "module": self.module,
            "level": record.levelname.lower(),
            "created": record.created,
            "message": record.msg % record.args
        }

        msg = amqp.basic_message.Message(body=json.dumps(message))

        try:
            self.channel.basic_publish(msg, exchange='log', routing_key=record.levelname.lower())
        except (BrokenPipeError, ConnectionResetError):
            # In some error cases logger might try to log after the disconnection
            self.channel = None


if __name__ == "__main__":
    """
        Testing...
    """

    connection = amqp.Connection(host='localhost:5672')
    channel = connection.channel()

    logger = logging.getLogger("mcc")
    logger.setLevel(logging.DEBUG)
    handler_messages = AMQPLogHandler("test", channel)
    logger.addHandler(handler_messages)

    logger.info("Wou! Life is amaizing")
    logger.warning("Wait! What! Something is wrong....")
    logger.error("Ouch! This must hurt!")
    logger.critical("Nooo! No I'm dying!")

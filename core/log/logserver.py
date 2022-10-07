"""
    Simple Log message cache to serve old log messages for the GUI
    Maybe could also do something else...

"""

import json
import uuid
import logging
from os.path import join as path_join

import aiormq
from porthouse.core.basemodule_async import BaseModule, rpc, queue, bind


class LogServer(BaseModule):
    """
    LogServer implementation
    """

    LOG_LEVELS = ["debug", "info", "warning", "error", "critical"]
    HISTORY_SIZE = 500

    def __init__(self, log_path: str, **kwarg):
        """
        Initialize module privates.
        """
        self.log_list = []
        self.log_path = log_path
        BaseModule.__init__(self, log_path=log_path, **kwarg)


    def create_log_handlers(self, log_path, module_name):
        """
            Override Basemodules original log handler creation
        """

        self.log = logging.getLogger("mcc")
        self.log.setLevel(logging.INFO)

        if True:
            # File log handler
            log_file = path_join(self.log_path, module_name + ".log")
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=2e6, backupCount=5)
            file_handler.setFormatter(formatter)
            self.log.addHandler(file_handler)


    @queue("log_recorder")  # Name the queue so it wont be recreated everytime
    @bind(exchange="log", routing_key="*")
    async def log_event(self, msg: aiormq.types.DeliveredMessage) -> None:
        """
        Store log entry to cache
        """

        try:
            log_entry = json.loads(msg.body)
        except:
            self.log.error('Error while parsing json message %s', msg.body, exc_info=True)
            return

        # Assign ID for the entry
        log_entry["id"] = str(uuid.uuid4())

        # Append to log cache
        self.log_list.append(log_entry)

        #
        if len(self.log_list) > self.HISTORY_SIZE:
            self.log_list.pop(0)


    @rpc()
    @bind(exchange="log", routing_key="rpc.get_history")
    async def rpc_callbacks(self, request_name: str, request_data: dict):
        """
        Handle RPC commands

        Args:
            request_name: Name of the RPC command
            request_data: Command arguments
        """

        if "before" in request_data:
            try:
                idx = [c["id"] for c in self.log_list].index(request_data["before"])
                entries = self.log_list[:idx]
            except (ValueError, KeyError):
                entries = []

        else:
            entries = self.log_list

        # Limit maximum number of items
        limit = int(request_data.get("limit", 60))

        return {"entries": entries[-limit:]}


if __name__ == "__main__":
    LogServer(
        log_path="./",
        amqp_url="amqp://guest:guest@localhost:5672/",
        debug=True
    ).run()

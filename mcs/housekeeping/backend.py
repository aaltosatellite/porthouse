"""
    Housekeeping backend module
"""

import json
from datetime import datetime

import aiormq

from porthouse.core.basemodule_async import BaseModule, RPCError, rpc, queue, bind
from .database import HousekeepingDatabase, DatabaseError
from ...core import config


class HousekeepingBackend(BaseModule):

    def __init__(self, hk_schema_path: str, db_url: str, **kwargs):
        """
        Init the housekeeping backend

        Args:
            schema_path
            db_url:

        """
        BaseModule.__init__(self, **kwargs)
        self.db = HousekeepingDatabase(hk_schema_path, db_url)


    @queue()
    @bind(exchange='housekeeping', routing_key='store', prefixed=True)
    async def housekeeping_store_callback(self, msg: aiormq.abc.DeliveredMessage):
        """
        Callback to store new data to database
        """
        try:
            json_message = json.loads(msg.body)
            assert isinstance(json_message, dict)
        except ValueError as e:
            self.log.warning("Error while parsing json msg:\n%s\n%s", msg.body, e.args[0])
            return

        # Check that mandatory fields have been provided
        for required in ["subsystem", "timestamp", "housekeeping"]:
            if required not in json_message:
                self.log.error("Store missing argument %r", required)
                return


        # Parse fields
        subsystem = json_message["subsystem"]
        timestamp = json_message["timestamp"]
        values = json_message["housekeeping"]
        source = json_message.get("source", None)
        metadata = json_message.get("metadata", {})

        if isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp)
        elif isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        else:
            self.log.error("Database error: invalid timestamp type %r", timestamp)
            return

        try:
            # Calibrate necessary values
            #values = self.db.calibrate_frame(subsystem, values)

            # Push the housekeeping entry to database
            self.db.insert_subsystem_frame(subsystem,timestamp,source,metadata,values)
        except DatabaseError as e:
            self.log.error("Database error: %s", str(e))
        else:
            self.log.debug("Stored hk frame: %s", str(json_message)[:100])

        json_message["housekeeping"] = values
        ## TODO: Chek limits
        #for limit in elem.findall("limit"):
        #    pass

        # Relay the updated telemetry to gui
        await self.publish(json_message, exchange='housekeeping', routing_key='update', prefixed=True)



    @rpc()
    @bind("housekeeping", "rpc.#", prefixed=True)
    def rpc_handler(self, request_name: str, request_data: dict):
        """
        """

        if request_name == "rpc.history":
            """
                Return housekeeping history
            """

            try:
                data = self.db.query(**request_data)
            except TypeError as e:
                if "missing" in str(e):
                    arg = str(e).split("'")[1]
                    raise RPCError(f"Request missing argument {arg!r}")
                elif "unexpected" in str(e):
                    arg = str(e).split("'")[1]
                    raise RPCError(f"Unknown argument {arg!r}")
                raise


            for row in data:
                row["timestamp"] = row["timestamp"].timestamp()

            return {
                "subsystem": request_data["subsystem"],
                "housekeeping": data
            }

        elif request_name == "rpc.latest":

            try:
                # Get latest housekeeping values
                latest = self.db.query_latest(**request_data)
            except TypeError as e:
                if "missing" in str(e):
                    arg = str(e).split("'")[1]
                    raise RPCError(f"Request missing argument {arg!r}")
                elif "unexpected" in str(e):
                    arg = str(e).split("'")[1]
                    raise RPCError(f"Unknown argument {arg!r}")
                raise

            # Format the datestring
            latest["timestamp"] = latest["timestamp"].timestamp()

            return {
                "subsystem": request_data["subsystem"],
                "housekeeping": latest
            }

        elif request_name == "rpc.schema":
            """
                Return housekeeping JSON schema
            """
            return { "schema": self.db.schema }

        else:
            raise RPCError("No such command")



if __name__ == '__main__':
    HousekeepingBackend(
        hk_schema_path="../foresail/housekeeping.json",
        db_url="postgres://mcs:PASSWORD@localhost/foresail",
        amqp_url="amqp://guest:guest@localhost:5672/",
        debug=True
    ).run()

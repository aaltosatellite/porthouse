from .database import MeasurementsDatabase, MeasurementsError
from porthouse.core.basemodule_async import BaseModule, RPCError, rpc, queue, bind
import aiormq
import math
import json
from datetime import datetime

class PacketMeasurementsBackend(BaseModule):

    def __init__(self, db_url: str, **kwargs):
        """
        Init the housekeeping backend

        Args:
            schema_path
            db_url:

        """
        BaseModule.__init__(self, **kwargs)
        self.db = MeasurementsDatabase(db_url)


    @queue()
    @bind(exchange='measurements', routing_key='fs1p.store.signaldata')
    async def measurements_store_callback(self, msg: aiormq.abc.DeliveredMessage):
        """
        Callback to store new data to database
        """
        try:
            json_message = json.loads(msg.body)
            assert isinstance(json_message, dict)
        except ValueError as e:
            self.log.warning("Error while parsing json msg:\n%s\n%s", msg.body, e.args[0])
            return
        
        snr = 10 * math.log10(json_message["pl_power"] / json_message["noise_power"]) if json_message["noise_power"] is not 0.0 else None
        
        self.db.insert_packet_measurement(
            json_message["t_unix"],
            json_message["rx_f_absolute"],
            json_message["pl_power"],
            json_message["noise_power"],
            snr,
            json_message["power_bw"],
            json_message["baudrate"],
            json_message["pl"]
        )
        utc = datetime.fromtimestamp(json_message["t_unix"]).isoformat().replace('+00:00', 'Z')
        publish_message = {
            "utc": utc,
            "fields": {
                "absolute_rx_frequency": json_message["rx_f_absolute"],
                "payload_power": json_message["pl_power"],
                "noise_power": json_message["noise_power"],
                "signal_to_noise_ratio": snr,
                "power_bandwidth": json_message["power_bw"],
                "baudrate": json_message["baudrate"],
                "pl": json_message["pl"]
            }
        }
            

        await self.publish(publish_message, exchange='measurements', routing_key='fs1p.update.signaldata')




    
        



if __name__ == '__main__':
    PacketMeasurementsBackend(
        hk_schema_path="../foresail/housekeeping.json",
        db_url="postgres://mcs:PASSWORD@localhost/foresail",
        amqp_url="amqp://guest:guest@localhost:5672/",
        debug=True
    ).run()

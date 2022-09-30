
Packets Router
###############

The Packet Router module is route between different transport protocols and translate packets between different formats.
For example the router can collect packets from AMQP exchange in JSON format, translate the packet to raw binary and transmit ito ZMQ publisher socket. This

The routering table is also reconfigurable.



Packet Formats
--------------

In the porthouse system

For example, a JSON formatted frame

... code-block: json

    {
        "timestamp": "2020-04-20T10:16:09.771568",
        "data": "0bs82c7d9a7ea010a8cdf99f0f",
        "source": "oh2ags",
        "packet_type": "telemetry",
        "metadata" {
            "rssi": -104.2
        }
    }


Following

- router_formatter_raw.json_to_raw
- router_formatter_raw.raw_to_json
- router_formatter_gnuradio.from_pmt
- router_formatter_gnuradio.to_pmt
- router_formatter_skylink.to_skylink
- router_formatter_skylink.from_skylink
- router_formatter_suo.to_suo
- router_formatter_suo.from_suo

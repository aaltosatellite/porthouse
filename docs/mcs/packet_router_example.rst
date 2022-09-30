
Packet Router example

... code-block: yaml

    - name: PacketRouter
      module: porthouse.mcs.packets.packet_router.PacketRouter
      params:
      - name: endpoint
        value:
        - name: aalto_raw_up
          type: zmq-sub
          connect: tcp://192.168.10.5:4001
          packet_type: raw_tc
          satellite: Foresail-1
          source: oh2ags
          multipart: True
          formatter: porthouse.mcs.packets.router_formatter_suo.from_suo

        - name: aalto_raw_down
          type: zmq-sub
          connect: tcp://192.168.10.5:4000
          packet_type: raw_tm
          satellite: Foresail-1
          source: oh2ags
          multipart: True
          formatter: porthouse.mcs.packets.router_formatter_suo.from_suo

        - name: json_telemetry
          type: zmq-sub
          bind: tcp://127.0.0.1:5400

        - name: aalto_up
          type: zmq-pub
          connect: tcp://192.168.10.5:5100
          packet_type: tc
          source: oh2ags
          formatter: porthouse.mcs.packets.router_formatter_skylink.to_skylink

        - name: aalto_down_9600
          type: zmq-sub
          connect: tcp://192.168.10.5:5000
          packet_type: tm
          source: oh2ags
          formatter: porthouse.mcs.packets.router_formatter_skylink.from_skylink

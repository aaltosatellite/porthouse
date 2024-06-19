
Packets Storage
###############

The Packet Storage is the packet/frame database used to store all packetized data handled by the mission control system.
The database can stores the packets as byte strings and store various frame types such as telemetry frames, telecommand frames, raw frames etc. Essentially, it just the al. The Packets Storage module can collect frames from various sources such as AMQP queues or ZMQ sockets as subscriber. These frame sources are called `links` and they are expected to json formatted
Ideally, the Packet Storage module




Installing
----------

To install Packet Storage module, first setup the PostgreSQL as described in TBD.
After setting up PSQL database and updating the `db_url` in porthouse globals accordingly, the packet database can be initialized using following command:

.. code-block:: bash

    $ porthouse packets --create_tables


Configuring
-----------

To configure

.. code-block:: yaml

    - name: PacketStorage
      module: porthouse.mcs.packets.packet_storage.PacketStorage
      params:
      - name: links
        value:
          - type: zmq
            bind: tcp://127.0.0.1:7600
          - type: amqp
            exchange: foresail1
            routing_key: "*.tc"
            packet_type: tc
            satellite: Foresail-1

          - type: amqp
            exchange: foresail1
            routing_key: "*.tm"
            packet_type: tm
            satellite: Foresail-1


Accessing the database
----------------------

The frame database can be easily access:

.. code-block:: python

    from porthouse.core.config import load_globals
    from porthouse.mcs.packets import PacketsDatabase

    db = PacketsDatabase(load_globals()["db_url"])

    for entry in db.query(satellite="Foresail-1", packet_type="tm", \
        start_date="2022-06-09T00:00:00", end_date="2022-06-12T00:00:00"):

        print(entry)







... code-block:: console

    $ porthouse packets --help
    usage: packets.py [-h] [--amqp AMQP] [--db DB] [--satellite SATELLITE]
                      [--type TYPE] [--source SOURCE] [--after AFTER]
                      [--before BEFORE] [--create_tables] [--totals] [--export]
                      [--cron]

    Packets database

    optional arguments:
      -h, --help            show this help message and exit
      --amqp AMQP           AMQP connection URL
      --db DB               PostgreSQL database URL. If not given environment
                            variable MCC_DB_ACCESS is used.
      --satellite SATELLITE
                            Filter results by the satellite identifier/name
      --type TYPE           Filter results by packet type
      --source SOURCE       Filter results by packet source
      --after AFTER         Filter results by timestamp
      --before BEFORE       Filter results by timestamp
      --create_tables       If given a default packets table will be created to
                            given the database.
      --totals              Get total number of bytes stored in the database
      --export
      --cron




Listing the routing table
-------------------------

... code-block:: console

    $ porthouse packets --routes

    # ENDPOINTS:
    Name:           | Type:           | Metadata:
    ----------------|-----------------|-----------------
    aalto_raw_up    | zmq-sub         |
    aalto_raw_down  | zmq-sub         |
    raw_db          | zmq-pub         |
    json_telemetry  | zmq-sub         |
    aalto_up        | zmq-pub         |
    aalto_down      | zmq-sub         |
    foresail_tc     | amqp-in         |
    foresail_tm     | amqp-out        |

    # ROUTES:
    Source          | Destination
    ----------------|-----------------
    aalto_raw_up    | raw_db
    aalto_raw_down  | raw_db
    json_telemetry  | foresail_tm
    aalto_down      | foresail_tm
    foresail_tc     | aalto_up




Changing routing table
----------------------

... code-block:: console

    $ porthouse packets --route foresail_tc egse_up

# Packet storage

`packet_router.py`: PacketStorage module itself
`database_api.py`: Packets database access class


# Packet router


`packet_router.py`: PacketRouter module itself
`router_endpoints.py`:
`router_formatter_*.py` -files



# Tools

## Packets command line interface

`packets.py` allow to access and do certain operations to the packets database.

```
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
```

For example to initialize packets table:
```
./packets.py --create_tables --db postgres://mcs:PASSWORD@localhost/foresail
```


## Telemetry replayer

## SatNOGS importer



# MCS's internal JSON packet format

For coding reference:
```
{
    "timestamp": "2020-04-20T10:16:09.771568",
    "data": "0bs82c7d9a7ea010a8cdf99f0f",
    "source": "oh2ags",
    "packet_type": "telemetry",
    "metadata" {
        "something": 1
    }
}
```

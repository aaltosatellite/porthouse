"""
    Class to interface with Postgres
"""

import json
from datetime import datetime, timedelta

import psycopg2
import psycopg2.extras

from urllib.parse import urlparse
from porthouse.core.db_tools import check_table_exists

class PacketsDatabaseError(RuntimeError):
    """ Generic class for database api errors """
    pass


def format_timestamp(t):
    """
        Format a unix timestamp or datetime for SQL query
    """
    if isinstance(t, datetime):
        return t.isoformat()
    if isinstance(t, int) or isinstance(t, float):
        return datetime.utcfromtimestamp(t).isoformat()
    if not isinstance(t, str):
        raise ValueError("Cannot convert {t!r} to timestamp")
    return t


class PacketsDatabase:
    """
    Database API for packet backend
    """

    def __init__(self, db_url=None, create_tables=False):
        """
            Initialize packet database connection
        """

        if db_url is None:
            import os
            if "MCC_DB_ACCESS" in os.environ:
                db_url = os.environ["MCC_DB_ACCESS"]
            else:
                raise ValueError("No database URL given!")

        # Connect using psycopg2
        db_url = urlparse(db_url)
        self.connection = psycopg2.connect("dbname='{0}' user='{1}' host='{2}' password='{3}'".format(
            db_url.path[1:], db_url.username, db_url.hostname, db_url.password))

        # Initialize database cursor
        self.cursor = self.connection.cursor()
        self.connection.autocommit = True

        if create_tables:
            self.create_tables()

        # Check table exists
        check_table_exists(self.cursor, "packets")

        #todo: check table is of correct format

    def create_tables(self):
        """
            Create database tables
        """

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS packets (
                id SERIAL,
                timestamp TIMESTAMP NOT NULL,
                source VARCHAR(16),
                satellite VARCHAR(16) NOT NULL,
                type VARCHAR(16) NOT NULL,
                data BYTEA NOT NULL,
                metadata JSON DEFAULT NULL
            );''')

        try:
            self.cursor.execute("SELECT create_hypertable('packets', 'timestamp');")
        except psycopg2.DatabaseError as e:
            print(e)

        self.connection.commit()


    def query(self,
              satellite,
              packet_type=None,
              source=None,
              start_date=None,
              end_date=None,
              with_id=False,
              with_metadata=False,
              limit=None,
              generator=False):
        """
            Query packets from the database
        """


        if start_date < end_date:
            start_date, end_date = end_date, start_date

        constraints = []
        constraints.append(f"satellite = {satellite!r}")

        if packet_type is not None:
            constraints.append(f"type = {packet_type!r}")
        if source is not None:
            constraints.append(f"source = {source!r}")
        if start_date is not None:
            constraints.append(f"timestamp <= {format_timestamp(start_date)!r}")
        if end_date is not None:
            constraints.append(f"timestamp >= {format_timestamp(end_date)!r}")

        if limit is None:
            limit = 50

        fields = ["timestamp", "type", "source", "data"]
        if with_metadata:
            fields.append("metadata")

        self.cursor.execute(f"""
            SELECT {", ".join(fields)}
            FROM packets
            WHERE {" AND ".join(constraints)}
            ORDER BY timestamp ASC
            LIMIT {limit!r};
        """)

        # Build RPC response
        for res in self.cursor:
            packet = {
                "timestamp": res[0],
                "type": res[1],
                "source": res[2],
                "data": res[3].tobytes()
            }
            if with_metadata:
                packet["metadata"] = res[4]
            yield packet

    def store_packet(self, source, satellite, packet_type, data, timestamp=None, metadata={}, **kwargs):
        """
            Store a packet to database
        """

        if timestamp is None:
            timestamp = datetime.now().isoformat()
        elif isinstance(timestamp, int) or isinstance(timestamp, float):
            timestamp = datetime.utcfromtimestamp(timestamp)

        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        # Push extra arguments to metadata so they won't get lost
        metadata.update(kwargs)
        metadata = json.dumps(metadata)

        # Create SQL insert query
        smt  = "INSERT INTO packets(satellite, source, timestamp, type, data, metadata) "
        smt += f"VALUES ({satellite!r}, {source!r}, {timestamp!r}, {packet_type!r}, {psycopg2.Binary(data)}, {metadata!r})"
        smt += "RETURNING id;"

        self.cursor.execute(smt)
        r = self.cursor.fetchone()  # Get the ID of newly created packet

        if r is None:
            raise RuntimeError("Failed to retrieve packet id!")


    def is_duplicate(self, timestamp, data):
        """
            Check whether the given packet is already in the database
        """

        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        start_time = timestamp - timedelta(hours=12)
        end_time = timestamp + timedelta(hours=12)

        self.cursor.execute(f"""
            SELECT COUNT(*)
            FROM packets
            WHERE timestamp > {start_time.isoformat()!r}
            AND timestamp < {end_time.isoformat()!r}
            AND data = {psycopg2.Binary(data)};
        """)

        c = self.cursor.fetchone()
        print(c)
        return response


    def set_metadata(self, new_metadata, extend=True):
        """
        """

        self.cursor.execute('''
            SELECT metadata FROM packets
            WHERE type="tc" AND id=""
            ORDER BY id DESC
        ''', data)
        self.db_connection.fetch()

        for data in self.cursor.fetchall():

            metadata = data[0]
            metadata.extend(new_metadata)

            self.cursor.execute('''
                UPDATE packets
                SET metadata=:ack_value
                WHERE id=%(packet_id)d
            ''', data)


if __name__ == "__main__":
    import sys
    from porthouse.core.config import load_globals
    cfg = load_globals()
    PacketsDatabase(
        db_url=cfg["db_url"],
        create_tables=("--create_tables" in sys.argv)   
    )



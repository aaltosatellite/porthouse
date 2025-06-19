import json
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
from typing import Optional, Union, Sequence

from urllib.parse import urlparse
from porthouse.core.db_tools import check_table_exists

DatetimeTypes = Union[datetime, int, float, str]

class MeasurementsError(RuntimeError):
    """ Generic class for database API errors """

class MeasurementsDatabase:
    
    connection: Optional[psycopg2.extensions.connection]
    cursor: Optional[psycopg2.extensions.cursor]
    
    def __init__(self,
                 db_url: Optional[str]=None,
                 create_tables: bool=False) -> None:
        """
        Initialize the MeasurementsDatabase class.
        Args:
            db_url: Database connector URL ("postgres://user:password@host/database")
            create_tables: If True, create the packet_measurements table if it does not exist.
        """
        self.connection = None
        self.cursor = None

        # Connect to SQL database if url provided
        if db_url is not None:
            self._db_connect(db_url)
            
        if self.cursor is not None and not check_table_exists(self.cursor, "packet_measurements") and create_tables:
            self._create_table()
    
    def _create_table(self):
        fields = [
            "id SERIAL",
            "timestamp TIMESTAMP NOT NULL",
            "absolute_rx_frequency FLOAT NOT NULL",
            "payload_power FLOAT NOT NULL",
            "noise_power FLOAT NOT NULL",
            "signal_to_noise_ratio FLOAT NOT NULL",
            "power_bandwidth FLOAT NOT NULL",
            "baudrate INT NOT NULL",
            "payload VARCHAR(512) NOT NULL",
        ]
        stmt = f"CREATE TABLE IF NOT EXISTS packet_measurements (\n  " + ",\n  ".join(fields) + "\n);"
        print("Executing: ")
        print(stmt)
        self.cursor.execute(stmt)
        
        # Creates timescaledb hypertable from table.
        try:
            stmt = f"SELECT create_hypertable('packet_measurements', 'timestamp')"
            self.cursor.execute(stmt)
        except psycopg2.DatabaseError as e:
            print("WARNING:", str(e))
            
            
    def _db_connect(self, db_url: str) -> None:
        """
        Connect to the database.

        Args:
            db_url: Database connector URL ("postgres://user:password@host/database")
        """

        parsed = urlparse(db_url)
        self.connection = psycopg2.connect(
            dbname=parsed.path[1:], # Remove the first slash
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port,
        )

        self.connection.autocommit = True
        self.cursor = self.connection.cursor()

    def create_time_constraint(self,
            start_date: DatetimeTypes,
            end_date: DatetimeTypes
        ) -> str:
        """ Create constraint str for SQL query from str or datetime dates. """

        if isinstance(start_date, datetime):
            start_date = start_date.isoformat()
        if isinstance(start_date, (int, float)):
            start_date = datetime.fromtimestamp(start_date, tz=timezone.utc).isoformat()

        if isinstance(end_date, datetime):
            end_date = end_date.isoformat()
        if isinstance(end_date, (int, float)):
            end_date = datetime.fromtimestamp(end_date, tz=timezone.utc).isoformat()

        return f"timestamp >= '{end_date}' AND timestamp <= '{start_date}'"

        
    def query(self,
              fields: Union[str, Sequence[str]],
              start: DatetimeTypes,
              end: DatetimeTypes) -> list:
        """
        Query packet measurements between end time and start time.
        start: Start datetime for the query
        end: End datetime of the query
        """
        if self.cursor is None:
            raise MeasurementsError("No database connection!")
        
        columns = [ "timestamp" ]

        for field_name in fields:
            columns.append(field_name)
        
        if start < end:
            start, end = end, start


        time_constraint = self.create_time_constraint(start, end)
        stmt = f"SELECT {', '.join(columns)} FROM packet_measurements WHERE {time_constraint} ORDER BY timestamp DESC;"
        try:
            self.cursor.execute(stmt)
        except psycopg2.DatabaseError as e:
            raise MeasurementsError(f"Database error: {str(e)}")
        columns = [desc[0] for desc in self.cursor.description]
        results = []
        for line in self.cursor.fetchall():
            row = dict(zip(columns, line))
            # Convert 'timestamp'
            if "timestamp" in row:
                if isinstance(row['timestamp'], datetime):
                    row['timestamp'] = row['timestamp'].replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
                    row["utc"] = row['timestamp']
                    del row["timestamp"]                
            results.append(row)
        return results
    
    def query_latest(self,
                     fields: Union[str, Sequence[str]],
                     start: DatetimeTypes,
                     end: DatetimeTypes) -> Optional[dict]:
        """
        Query latest packet measurements between end time and start time.
        """
        
        if self.cursor is None:
            raise MeasurementsError("No database connection!")
        
        columns = [ "timestamp" ]

        for field_name in fields:
            columns.append(field_name)
        
        if start < end:
            start, end = end, start

        time_constraint = self.create_time_constraint(start, end)

        stmt = f"SELECT {', '.join(columns)} FROM packet_measurements WHERE {time_constraint} ORDER BY timestamp DESC LIMIT 1;"
        try:
            self.cursor.execute(stmt)

            data = self.cursor.fetchone()
            if not data:
                return None
            colnames = [desc[0] for desc in self.cursor.description]

            x = dict(zip(colnames, data))
            x["timestamp"] = x["timestamp"].replace(tzinfo=timezone.utc)
            return x

        except psycopg2.ProgrammingError as e:
            raise MeasurementsError(str(e)) from e

        
        
    def insert_packet_measurement(self,
                    timestamp: DatetimeTypes,
                    absolute_rx_frequency: float,
                    payload_power: float,
                    noise_power: float,
                    signal_to_noise_ratio: float,
                    power_bandwidth: float,
                    baudrate: int,
                    payload: str,
                     ) -> None:
        """ Insert packet measurement into the database. """
        if self.cursor is None:
            raise MeasurementsError("No database connection!")
        if isinstance(timestamp, datetime):
            timestamp = timestamp.replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
        if isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace('+00:00', 'Z')

        stmt = """
        INSERT INTO packet_measurements (timestamp, absolute_rx_frequency, payload_power, noise_power, signal_to_noise_ratio, power_bandwidth, baudrate, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """
        try:
            self.cursor.execute(stmt, (
                timestamp,
                absolute_rx_frequency,
                payload_power,
                noise_power,
                signal_to_noise_ratio,
                power_bandwidth,
                baudrate,
                payload
            ))
        except psycopg2.DatabaseError as e:
            raise MeasurementsError(f"Database error: {str(e)}")

if __name__ == "__main__":
    import sys
    from porthouse.core.config import load_globals
    cfg = load_globals()
    if (len(sys.argv) == 2) and (sys.argv[1] == "--create_tables"):
        MeasurementsDatabase(
            db_url=cfg["db_url"],
            create_tables=True
        )
        print("Done.")
        exit()
    else:
        print("Usage: python3 database.py --create_tables")
        exit(1)
import json
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
from typing import Optional, Union

from urllib.parse import urlparse
from porthouse.core.db_tools import check_table_exists

DatetimeTypes = Union[datetime, int, float, str]

class EventsError(RuntimeError):
    """ Generic class for database API errors """

class EventsDatabase:
    
    connection: Optional[psycopg2.extensions.connection]
    cursor: Optional[psycopg2.extensions.cursor]
    
    def __init__(self,
                 db_url: Optional[str]=None,
                 create_tables: bool=False) -> None:
        """
        Initialize the EventsDatabase class.
        Args:
            db_url: Database connector URL ("postgres://user:password@host/database")
            create_tables: If True, create the events table if it does not exist.
        """
        self.connection = None
        self.cursor = None

        # Connect to SQL database if url provided
        if db_url is not None:
            self._db_connect(db_url)
            
        if self.cursor is not None and not check_table_exists(self.cursor, "events") and create_tables:
            self._create_table()
    
    def _create_table(self):
        fields = [
            "id SERIAL",
            "timestamp TIMESTAMP UNIQUE NOT NULL",
            "received TIMESTAMP NOT NULL",
            "severity VARCHAR(256) NOT NULL",
            "data VARCHAR(256) NOT NULL",
            "event_name VARCHAR(256) NOT NULL",
            "source VARCHAR(256) NOT NULL",
        ]
        
        stmt = f"CREATE TABLE IF NOT EXISTS events (\n  " + ",\n  ".join(fields) + "\n);"
        print("Executing: ")
        print(stmt)
        self.cursor.execute(stmt)
        
        # Creates timescaledb hypertable from table.
        try:
            stmt = f"SELECT create_hypertable('events', 'timestamp')"
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
              start: DatetimeTypes,
              end: DatetimeTypes) -> list:
        """
        Query events between end time and start time.
        start: Start datetime for the query
        end: End datetime of the query
        """
        if self.cursor is None:
            raise EventsError("No database connection!")
        
        if start < end:
            start, end = end, start

        time_constraint = self.create_time_constraint(start, end)
        stmt = f"SELECT * FROM events WHERE {time_constraint} ORDER BY timestamp DESC;"
        self.cursor.execute(stmt)
        columns = [desc[0] for desc in self.cursor.description]
        results = []
        for line in self.cursor.fetchall():
            row = dict(zip(columns, line))
            # Convert 'timestamp' and 'received'
            for key in ['timestamp', 'received']:
                if isinstance(row[key], datetime):
                    row[key] = row[key].replace(tzinfo=timezone.utc).isoformat().replace('+00:00', 'Z')
                    if key == "timestamp":
                        row["utc"] = row[key]
            # Drop timestamp column if it exists
            if "timestamp" in row:
                del row["timestamp"]
            results.append(row)
        return results
        
    def insert_event(self,
                     timestamp: DatetimeTypes,
                     received: DatetimeTypes,
                     severity: str,
                     data: str,
                     event_name: str,
                     source: str) -> None:
        """ Insert event into the database. """
        if self.cursor is None:
            raise EventsError("No database connection!")
        
        # Convert datetime or timestamp to ISO format if needed
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()
        if isinstance(received, datetime):
            received = received.isoformat()

        if isinstance(timestamp, (int, float)):
            timestamp = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
        if isinstance(received, (int, float)):
            received = datetime.fromtimestamp(received, tz=timezone.utc).isoformat()

        # Prepare the SQL statement
        stmt = """INSERT INTO events (timestamp, received, severity, data, event_name, source)
        VALUES (%s, %s, %s, %s, %s, %s);"""
        values = (timestamp, received, severity, data, event_name, source)
        try:
            self.cursor.execute(stmt, values)
        except psycopg2.DatabaseError as e:
            raise EventsError(f"Failed to insert event: {str(e)}")

if __name__ == "__main__":
    import sys
    from porthouse.core.config import load_globals
    cfg = load_globals()
    if (len(sys.argv) == 2) and (sys.argv[1] == "--create_tables"):
        EventsDatabase(
            db_url=cfg["db_url"],
            create_tables=True
        )
        print("Done.")
        exit()
    else:
        print("Usage: python3 database.py --create_tables")
        exit(1)
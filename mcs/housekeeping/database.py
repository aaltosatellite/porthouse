import json
import psycopg2
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Any, Dict, Generator, List, Optional, Sequence, Union

from porthouse.core.db_tools import check_table_exists
from porthouse.mcs.housekeeping.parsing import Subsystem, Field, load_subsystems



class HousekeepingError(RuntimeError):
    """ Generic class for database API errors """

class DatabaseError(HousekeepingError):
    """ Class for housekeeping database access errors """

class SchemaError(HousekeepingError):
    """ Class for Housekeeping schema error """


# Data type mapping from raw types to SQL data types
RAW2PSQL = {
    "int8": "SMALLINT",
    "uint8": "SMALLINT",
    "int16": "INT",
    "uint16": "INT",
    "int32": "INT",
    "uint32": "BIGINT",
    "float": "REAL",
    "double": "DOUBLE PRECISION"
}

FMT2PSQL = {
    "integer": "BIGINT",
    "float": "REAL",
    "double": "DOUBLE PRECISION",
    "binary": "INT",
    "hex": "INT",
    "enumeration": "VARCHAR(256)",
    "string": "VARCHAR(256)"
}

DatetimeTypes = Union[datetime, int, float, str]
HousekeepingEntry = Dict[str, Any]




class HousekeepingDatabase:
    """
    Housekeeping schema and database access class.
    """

    connection: Optional[psycopg2.extensions.connection]
    cursor: Optional[psycopg2.extensions.cursor]

    subsystems: Dict[str, Subsystem]

    def __init__(self,
            schema_path: str,
            db_url: Optional[str]=None,
            create_tables: bool=False
        ):
        """
        Load housekeeping schema and connect to the SQL database.

        Args:
            db_url: Optional database connection URL. See .connect()
            schema_path: Filepath to housekeeping JSON schema file
            create_tables:
        """
        self.connection = None
        self.cursor = None

        # Connect to SQL database if url provided
        if db_url is not None:
            self._db_connect(db_url)

        self.subsystems = load_subsystems(schema_path)

        if self.cursor is not None:
            for subsystem in self.subsystems.values():
                if not check_table_exists(self.cursor, subsystem.key):
                    self._create_table(subsystem)
                #self._validate_subsystem_table(subsystem)


    def _create_table(self, subsystem: Subsystem) -> None:
        """
        Creates database table if not already existing.

        Args:
            subsystem: Subsystem object
        """

        if self.cursor is None:
            raise HousekeepingError("No database connection!")


        fields = [
            "id SERIAL",
            "timestamp TIMESTAMP UNIQUE NOT NULL",
            "source VARCHAR(256) NOT NULL",
            "metadata JSON DEFAULT NULL",
        ]

        for field in subsystem.fields:

            try:
                # NOTE: enumerations do not have calibration but they need format
                #if hasattr(field, "calibration") or hasattr(self, "enumeration"):
                #    cal_type = FMT2PSQL[field.format]
                #else:
                #    cal_type = RAW2PSQL[field.raw]
                raw_type = RAW2PSQL[field.raw_type]
                cal_type = FMT2PSQL[field.format_type]

                fields.append(f"{field.key} {cal_type} NOT NULL")
                fields.append(f"{field.key}_raw {raw_type} DEFAULT NULL")

            except KeyError as e:
                raise SchemaError(f"{subsystem.key}.{field.key} missing field {e}")

        stmt = f"CREATE TABLE IF NOT EXISTS {subsystem.key} (\n  " + ",\n  ".join(fields) + "\n);"
        print(stmt)
        self.cursor.execute(stmt)
        #return

        # Creates timescaledb hypertable from table.
        try:
            stmt = f"SELECT create_hypertable('{subsystem.key}', 'timestamp')"
            self.cursor.execute(stmt)
        except psycopg2.DatabaseError as e:
            print("WARNING:", str(e))


    def _validate_subsystem_table(self, subsystem: Subsystem) -> None:
        """
        """

        STATIC_COLUMNS = [
            ('id',            'integer') ,
            ('timestamp',     'timestamp without time zone') ,
            ('source',        'character varying') ,
            ('metadata',      'json') ,
        ]

        # Query a list of columns in the table
        self.cursor.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name={subsystem.key!r};")
        columns = self.cursor.fetchall()

        # Check if there are "..._raw" fields in the database. If yes, then all table specific fields must have a _raw field
        include_raws = any(column_name.endswith("_raw") for column_name, _ in columns)

        # All tables begin with columns: id, timestamp, source, metadata
        for i, field_define in enumerate(STATIC_COLUMNS):
            if columns[i] != field_define:
                raise RuntimeError(f"Missing field {field_define[0]}")

        # Assert the number of columns match.
        if len(columns) - len(STATIC_COLUMNS) != len(subsystem.fields) * (1 + include_raws):
            raise RuntimeError(f"Column count does not match for table {subsystem.key!r}")

        # Assert all the columns names and datatypes match
        for i, field in enumerate(subsystem.fields):
            j = len(STATIC_COLUMNS) + i * (1 + include_raws)

            if columns[j][0] != field.key:
                raise RuntimeError(f"{columns[j][0]} != {field.key}")
            if columns[j][1] != FMT2PSQL[field.format]:
                raise RuntimeError(f"{field.key}: {columns[j][1]} != {FMT2PSQL[field.format]}")

            if include_raws:
                if columns[j+1][0] != field.key+"_raw":
                    raise RuntimeError(f"{columns[j+1][0]} != {field.key}_raw")
                if columns[j+1][1] != RAW2PSQL[field.raw]:
                    raise RuntimeError(f"{field.key}_raw: {columns[j+1][1]} != {RAW2PSQL[field.raw]}")


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


    def get_subsystem_object(self, key: str) -> Subsystem:
        """
        Get the subsystem schema object by the identifier key
        """
        try:
            return self.subsystems[key]
        except KeyError:
            raise DatabaseError(f"No such housekeeping frame {key!r}")


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
            subsystem_key: str,
            fields: Union[str, Sequence[str]],
            start_date: DatetimeTypes,
            end_date: DatetimeTypes,
            limit: Optional[int]=None,
            with_raw: bool=False,
            with_source: bool=False,
            with_metadata: bool=False,
            generator: bool=False
        ) -> Union[List[HousekeepingEntry], Generator[List[HousekeepingEntry], None, None]]:
        """
        Query housekeeping values from the database.

        Args:
            sybsystem_key: A string key to identify the subsystem
            fields: A list or tuple containing the names of queried housekeeping fields.
            start_date: Start datetime for the query
            end_time: End datetime of the query
            limit: Maximum number of
            with_raw: Include raw (uncalibrated) values to each query result
            with_source: Include housekeeping data source to each query result
            with_metadata: Include metadata field to each query result
            generator: If true a generator object is returned

        Returns:
            A list housekeeping entry dicts is returned.
        """

        if self.cursor is None:
            raise HousekeepingError("No database connection!")

        subsystem = self.get_subsystem_object(subsystem_key)

        if isinstance(fields, str):
            fields = [fields]
        elif not isinstance(fields, (list, tuple)):
            raise ValueError(f"Invalid fields paramater: {fields!r}")

        if start_date < end_date:
            start_date, end_date = end_date, start_date

        constraint = self.create_time_constraint(start_date, end_date)

        #if not subsystem.has_field(fields):
        #    raise HousekeepingError(f"No such housekeeping field {field_name!r}")

        columns = [ "timestamp" ]
        if with_source:
            columns.append("source")
        if with_metadata:
            columns.append("metadata")

        for field_name in fields:
            columns.append(field_name)
            if with_raw:
                columns.append(field_name + "_raw")


        stmt = f"SELECT {', '.join(columns)} FROM {subsystem.key} WHERE {constraint} ORDER BY timestamp DESC"
        if limit: stmt += f"LIMIT {limit}"
        stmt += ";"


        try:
            self.cursor.execute(stmt)
            if generator:
                for line in self.cursor:
                    yield dict(zip(columns, line))

            else:
                return list([ dict(zip(columns, line)) for line in self.cursor.fetchall() ])

        except psycopg2.ProgrammingError as e:
            raise DatabaseError(str(e)) from e


    def query_binned(self,
            subsystem_key: str,
            fields: Union[str, Sequence[str]],
            start_date: DatetimeTypes,
            end_date: DatetimeTypes,
            size: int,
            generator: bool=False
        ) -> Union[List[HousekeepingEntry], Generator[List[HousekeepingEntry], None, None]]:
        """
        Retrieve housekeeping values for the subsystem and bin.

        Args:
            subsystem_key: A string key to identify the subsystem
            fields: A list or tuple containing the names of queried housekeeping fields.
            start_date: Start datetime for the query
            end_time: End datetime of the query
            size: Number of the bins
            generator: If true, a generator object is returned instead of a list

        Returns:
            A list housekeeping entry dicts is returned.
        """

        if self.cursor is None:
            raise HousekeepingError("No database connection!")

        subsystem = self.get_subsystem_object(subsystem_key)

        if not isinstance(fields, (list, tuple)):
            fields = [ fields ]

        if start_date < end_date:
            start_date, end_date = end_date, start_date


        # Calculate the size of the bin/bucket
        bucket = (start_date - end_date).total_seconds() // size
        if bucket <= 1:
            return self.query(subsystem_key=subsystem_key, fields=fields, start_date=start_date, end_date=end_date, generator=generator)

        constraint = self.create_time_constraint(start_date, end_date)

        stmt = f"SELECT time_bucket('{bucket} seconds', timestamp) AS timestamp"
        for field_name in fields:
            if not subsystem.has_field(field_name):
                raise HousekeepingError(f"No such housekeeping field {field_name!r}")
            stmt += f", AVG({field_name}) AS {field_name}_avg"
            stmt += f", MIN({field_name}) AS {field_name}_min"
            stmt += f", MAX({field_name}) AS {field_name}_max"
        stmt += f" FROM {subsystem.key} WHERE {constraint} GROUP BY timestamp ORDER BY timestamp DESC;"

        try:
            self.cursor.execute(stmt)
            colnames = [desc[0] for desc in self.cursor.description]

            if generator:
                for line in self.cursor:
                    x = dict(zip(colnames, line))
                    x["timestamp"] = x["timestamp"].replace(tzinfo=timezone.utc)
                    yield x

            else:
                return list([ dict(zip(colnames, line)) for line in  self.cursor.fetchall() ])

        except psycopg2.ProgrammingError as e:
            raise DatabaseError(str(e))




    def query_latest(self,
            subsystem_key: str,
            fields: Union[str, Sequence[str]],
            start_date: Optional[DatetimeTypes]=None,
            end_date: Optional[DatetimeTypes]=None,
            with_raw: bool=False,
            with_source: bool=False,
            with_metadata: bool=False
        ) -> Optional[HousekeepingEntry]:
        """
        Retrieve latest housekeeping values for the subsystem.

        Args:
            sybsystem_key: A string key to identify the subsystem
            fields: A list or tuple containing the names of queried housekeeping fields.
            start_date: Start datetime for the query
            end_time: End datetime of the query
            limit: Maximum number of
            with_raw: Include raw (uncalibrated) values to each query result
            with_source: Include housekeeping data source to each query result
            with_metadata: Include metadata field to each query result

        Returns:
            A list housekeeping entry dicts is returned.
        """

        if self.cursor is None:
            raise HousekeepingError("No database connection!")

        subsystem = self.get_subsystem_object(subsystem_key)
        if not isinstance(fields, (list, tuple)):
            fields = [fields]

        constrains = []
        if start_date < end_date:
            start_date, end_date = end_date, start_date
        if start_date and end_date:
            constrains.append(self.create_time_constraint(start_date, end_date))

        stmt = "SELECT timestamp"
        if with_source:
            stmt += ", source"
        if with_metadata:
            stmt += ", metadata"
        for field_name in fields:
            stmt += f", {field_name}"
            if with_raw:
                stmt += f", {field_name}_raw"

        stmt += f" FROM {subsystem.key}"
        if len(constrains):
            stmt += " WHERE " + " AND ".join(constrains)
        stmt += " ORDER BY timestamp DESC "
        stmt += " LIMIT 1;"

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
            raise DatabaseError(str(e)) from e


    def insert_subsystem_frame(self,
            subsystem_key: str,
            timestamp: DatetimeTypes,
            source: Optional[str],
            metadata: Optional[Union[Dict, str]],
            fields: Dict[str, Any]
        ) -> None:
        """
        Inserts a new housekeeping frame into db.

        Args:
            substem_key: A string key to identify the subsystem
            timestamp: Time when
            source: Optional frame source name
            metadata: Optional dictionary of metadata

        """

        if self.cursor is None:
            raise HousekeepingError("No database connection!")


        subsystem = self.get_subsystem_object(subsystem_key)

        names, values = [], []
        for field in subsystem.fields:
            if field.key not in fields:
                raise HousekeepingError(f"Missing field {field.key}")
            names.append(field.key)
            values.append(repr(fields[field.key]))


        stmt  = f"INSERT INTO {subsystem.key} (timestamp, source, metadata, {', '.join(names)}) "
        stmt += f"VALUES ('{timestamp}', '{source}', '{json.dumps(metadata)}', {', '.join(values)} );"

        print(stmt)
        try:
            self.cursor.execute(stmt)
        except (psycopg2.IntegrityError, ValueError) as e:
            raise DatabaseError(str(e))


    def calibrate_frame(self,
            subsystem_key: str,
            values: HousekeepingEntry
        ) -> HousekeepingEntry:
        """
        Calibrates values for which calibration is necessary.

        Parses enumerations into their text representation.
        Parses bitfields into their text representation.

        Args:
            subsystem_key: A string key to identify the subsystem
            values: Dictionary containting the telemetry fields of a one entry

        Returns:

        """

        calibrated = { }
        subsystem = self.get_subsystem_object(subsystem_key)

        for field in subsystem.fields:
            try:
                raw = values[field.key]
            except KeyError:
                raise DatabaseError(f"Missing housekeeping value {subsystem_key}.{field.key}")

            if field.calibration:
                value = field.calibrate(raw)
            elif field.enumeration:
                value = field.parse_enum(raw)
            else:
                value = raw

            calibrated[field.key] = value
            calibrated[f"{field.key}_raw"] = raw

        return calibrated


    def parse_bytestream(self,
            subsystem_key: str,
            bytestream: bytes
        ) -> HousekeepingEntry:
        """
        Parses bytestream to dictionary used in the database api

        Args:
            subsystem_key:
            bytestream:
        """

        raise NotImplementedError("Parsing not yet implemented")



if __name__ == "__main__":
    import sys
    from porthouse.core.config import load_globals
    cfg = load_globals()
    if (len(sys.argv) == 3) and (sys.argv[1] == "--create_tables"):
        HousekeepingDatabase(
            db_url=cfg["db_url"],
            schema_path=sys.argv[2],
            create_tables=True
        )
        print("Done.")
        exit()
    else:
        print("Usage: python3 database.py --create_tables schema.json")
        exit(1)
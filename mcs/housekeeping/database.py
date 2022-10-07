import json
import psycopg2
from datetime import datetime
from urllib.parse import urlparse
from typing import Any, Dict, Generator, List, Optional, Sequence, Union

from porthouse.core.db_tools import check_table_exists
from .parsing import Subsystem, Field, load_subsystems


#TODO: fix time_bucket: 176.

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
    "enum": "VARCHAR(256)",
    "string": "VARCHAR(256)"
}

DatetimeTypes = Union[datetime, int, float, str]
HousekeepingEntry = Dict[str, Any]

#This is a rather ugly method in itself, but does its job.
def check_hk_table_format_correctness(cursor: psycopg2.extensions.cursor, subsystem:Subsystem, table_name:str) -> bool:

    static_columns = [
        ('id',            'integer') ,
        ('timestamp',     'timestamp without time zone') ,
        ('source',        'character varying') ,
        ('metadata',      'json') ,
    ]


    # Query the state of the table in database into a list of queried lines.
    column_query = """SELECT column_name, data_type FROM  information_schema.columns
                      WHERE table_name = '{}';""".format(table_name)
    cursor.execute(column_query)
    lines = []
    qry_line = cursor.fetchone()
    while not (qry_line is None):
        lines.append(qry_line)
        qry_line = cursor.fetchone()

    # Check if there are "..._raw" fields in the database. If yes, then all table specific fields must have a _raw field
    raws = True in [x[0].endswith("_raw") for x in lines]
    n_cols_per_field = 1+(raws*1)

    # All tables begin with columns: id,timestamp,source,metadata
    for i in range(len(static_columns)):
        if not lines[i] == static_columns[i]:
            return False

    # Assert the number of lines match.
    if not len(lines) - len(static_columns) == (len(subsystem.fields) * n_cols_per_field):
        return False

    # Assert all the columns names and datatypes match
    for i in range(len(subsystem.fields)):
        field = subsystem.fields[i]
        j = len(static_columns) + i * n_cols_per_field
        if not (lines[j][0] == field.key) and (lines[j][1] == FMT2PSQL[field.format]):
            return False
        if raws:
            if not (lines[j+1][0] == field.key+"_raw") and (lines[j+1][1] == RAW2PSQL[field.raw]):
                return False
    return True


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

        self.assert_table_structure()


    def assert_table_structure(self):
        ret = check_hk_table_format_correctness(self.cursor, self.subsystems["adcs"], "adcs")
        if not ret:
            raise DatabaseError("ADCS hk table structure is incorrect!")
        ret = check_hk_table_format_correctness(self.cursor, self.subsystems["obc"], "obc")
        if not ret:
            raise DatabaseError("OBC hk table structure is incorrect!")
        ret = check_hk_table_format_correctness(self.cursor, self.subsystems["uhf"], "uhf")
        if not ret:
            raise DatabaseError("UHF hk table structure is incorrect!")
        ret = check_hk_table_format_correctness(self.cursor, self.subsystems["eps"], "eps")
        if not ret:
            raise DatabaseError("EPS hk table structure is incorrect!")


    def _create_table(self, subsystem: Subsystem) -> None:
        """
        Creates database table if not already existing.

        Args:
            subsystem: Subsystem object
        """

        if self.cursor is None:
            raise HousekeepingError("No database connection!")

        cmd = f"CREATE TABLE IF NOT EXISTS {subsystem.key} ("
        cmd += "id SERIAL"
        cmd += ", timestamp TIMESTAMP UNIQUE NOT NULL"
        cmd += ", source VARCHAR(256) NOT NULL"
        cmd += ", metadata JSON DEFAULT NULL"

        for field in subsystem.fields:

            try:
                raw_type = RAW2PSQL[field.raw]
                #NOTE: enumerations do not have calibration but they
                #need format
                if field.calibration or field.enum:
                    cal_type = FMT2PSQL[field.format]
                else:
                    cal_type = RAW2PSQL[field.raw]

                tm_field = f", {field.key} {cal_type} NOT NULL"
                tm_field += f", {field.key}_raw {raw_type} DEFAULT NULL"
                cmd += tm_field

            except KeyError as e:
                raise SchemaError(f"{subsystem.key}.{field.key} missing field {e}")

        stmt = cmd + ");"

        self.cursor.execute(stmt)

        # Creates timescaledb hypertable from table.
        try:
            stmt = f"SELECT create_hypertable('{subsystem.key}', 'timestamp')"
            self.cursor.execute(stmt)
        except psycopg2.DatabaseError as e:
            print("WARNING:", str(e))


    def _db_connect(self, db_url: str) -> None:
        """
        Connect to the database.

        Args:
            db_url: Database connector URL ("postgres://user:password@host/database")
        """

        db_url = urlparse(db_url)
        self.connection = psycopg2.connect("dbname='{0}' user='{1}' host='{2}' password='{3}'".format(
            db_url.path[1:], db_url.username, db_url.hostname, db_url.password))
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
        if isinstance(start_date, int) or isinstance(start_date, float):
            start_date = datetime.utcfromtimestamp(start_date).isoformat()

        if isinstance(end_date, datetime):
            end_date = end_date.isoformat()
        if isinstance(end_date, int) or isinstance(end_date, float):
            end_date = datetime.utcfromtimestamp(end_date).isoformat()

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

        stmt = "SELECT timestamp"
        if with_source:
            stmt += ", source"
        if with_metadata:
            stmt += ", metadata"

        for field_name in fields:
            if not subsystem.has_field(field_name):
                raise HousekeepingError(f"No such housekeeping field {field_name!r}")
            stmt += f", {field_name}"
            if with_raw:
                stmt += f", {field_name}_raw"

        stmt += f" FROM {subsystem.key}"
        stmt += f" WHERE {constraint}"
        stmt += " ORDER BY timestamp DESC"
        if limit:
            stmt += f"LIMIT {limit}"
        stmt += ";"


        try:
            self.cursor.execute(stmt)
            colnames = [desc[0] for desc in self.cursor.description]

            if generator:
                for line in self.cursor:
                    yield dict(zip(colnames, line))

            else:
                return list([ dict(zip(colnames, line)) for line in self.cursor.fetchall() ])

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

        constraint = self.create_time_constraint(start_date, end_date)

        # Calculate the size of the bin/bucket
        bucket = (start_date - end_date) / size

        stmt = f"SELECT time_bucket('{bucket} seconds', timestamp) AS timestamp"
        for field_name in fields:
            if not subsystem.has_field(field_name):
                raise HousekeepingError(f"No such housekeeping field {field_name!r}")
            stmt += f", AVG({field_name}) AS {field_name}_avg"
            stmt += f", MIN({field_name}) AS {field_name}_min"
            stmt += f", MAX({field_name}) AS {field_name}_max"
        stmt += f" FROM {subsystem.key}"
        stmt += f" WHERE {constraint}"
        stmt += " GROUP BY bucket, timestamp"
        stmt += " ORDER BY bucket, timestamp DESC"
        stmt += ";"

        try:
            self.cursor.execute(stmt)
            colnames = [desc[0] for desc in self.cursor.description]

            if generator:
                for line in self.cursor:
                    yield dict(zip(colnames, line))

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
        ) -> HousekeepingEntry:
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

            return dict(zip(colnames, data))

        except psycopg2.ProgrammingError as e:
            raise DatabaseError(str(e)) from e


    def insert_subsystem_frame(self,
            subsystem_key: str,
            timestamp: DatetimeTypes,
            source: Optional[str],
            metadata: Optional[Union[Dict, str]],
            fields: Union[str, Sequence[str]]
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

        stmt = f"INSERT INTO {subsystem.key}(timestamp, source, metadata, "
        stmt += ", ".join([ field.id for field in subsystem.fields ]) + ") "

        stmt += f"VALUES ('{timestamp}', '{source}', '{json.dumps(metadata)}'"

        for field in subsystem.fields:
            if field.key not in fields:
                raise HousekeepingError(f"Missing field {field.key}")
            stmt += f", {fields[field.key]!r}"
        stmt += ");"

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
            elif field.enum:
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
    HousekeepingDatabase(
        db_url=cfg["db_url"],
        schema_path=cfg["hk_schema"],
        create_tables=("--create_tables" in sys.argv)
    )

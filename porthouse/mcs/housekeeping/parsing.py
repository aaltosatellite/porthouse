from __future__ import annotations

import json
import struct
from typing import Any, Dict, List, NamedTuple, Union, Optional, Iterable, Tuple

__all__ = [
    'Subsystem',
    'Field',
    'load_subsystems'
]


_lengths = {"float":4, "double": 8, "uint8":1, "uint16":2, "uint32":4, "uint64":8, "int8":1, "int16":2, "int32":4, }
_struct_map = {"float":"f", "uint8":"B", "uint16":"H", "uint32":"I", "uint64":"L", "int8":"b", "int16":"h", "int32":"i", }
_format_types = {"float":float, "integer":int, "enumeration": str, "string":str}


class Subsystem:
    """
    Class to hold housekeeping subsystem structure.
    """

    # Subsystem identifier string
    key: str

    # Readable name
    name: str

    # List of housekeeping fields
    fields: List[Field]


    def __init__(self,
            key: str,
            name: str,
            fields: List[Field]
        ):
        """
        Initialize
        """
        self.key = key
        self.name = name
        self.fields = fields
        self.total_length = sum([ k.length for k in self.fields ])


    def get_total_length(self):
        """
        """
        return self.total_length


    def parse_blob_for_printing(self, data: bytes) -> Dict[str, Any]:
        """
        Not used currently, but there was a plan to use this for printing the units as well.
        """
        if not isinstance(data, bytes):
            raise ValueError(f"'data' is not bytes but {type(data)}")
        if self.get_total_length() > len(data):
            raise ValueError(f"Insufficient bytes to parse fields determined by the schema file.\n" \
                             f"Expected for {self.key}: {self.get_total_length()}\nGot: {len(data)}")
        parse_output = dict()
        cursor = 0
        for field in self.fields:
            fmtd, raw = field.parse(data, cursor)   # returns the calibrated and raw values
            cursor += field.length
            if hasattr(field, "units"):
                parse_output[field.key] = (fmtd, field.units)
            else:
                parse_output[field.key] = (fmtd, "N/A")
        return parse_output


    def parse_blob_for_database(self, data: bytes, raw: bool=False):
        """
        """
        if not isinstance(data, bytes):
            raise ValueError(f"'data' is not bytes but {type(data)}")
        if self.get_total_length() > len(data):
            raise ValueError(f"Insufficient bytes to parse fields determined by the schema file.\n" \
                             f"Expected for {self.key}: {self.get_total_length()}\nGot: {len(data)}")
        parse_output = dict()
        cursor = 0
        for field in self.fields:
            fmtd, vraw = field.parse(data, cursor)   # returns the calibrated and raw values
            parse_output[field.key] = fmtd      # better name would be calibrated, not formatted
            if raw:
                parse_output[field.key + "_raw"] = vraw
            cursor += field.length
        return parse_output


    def has_field(self, field_name: str) -> bool:
        """
        Check
        """
        for field in self.fields:
            if field.key == field_name:
                return True
        return False


    def check_fields(self, field_names: str) -> bool:
        """
        Check
        """
        for field_name in field_names:
            if not self.has_field(field_name):
                raise RuntimeError(f"No such housekeeping field {field_name}")

CalibratedType = Union[int, float, str]

class Field:
    """
    Class to hold housekeeping field information.
    """

    # Field identifier
    key: str

    # Field name
    name: str

    # Type format
    format_type: str

    # Raw type
    raw_type: str

    # Physical units
    units: Optional[str]

    # Type enumeration definition
    enumeration: Optional[List[Dict[str,int]]]

    # Calibration
    calibration: Optional[List[float]]

    # Limits
    limits: Optional[List[int]] # TODO:


    def __init__(self,
            key: str,
            name: str,
            format_type: str,
            raw_type: str,
            units: Optional[str]=None,
            enumeration: Optional[int]=None,
            calibration: Optional[int]=None,
            limits: Optional[List[int]]=None,
            **kwargs
        ):
        """
        Initialize housekeeping field
        """

        if not isinstance(key, str) or len(key) == 0:
            raise ValueError(f"The key is not a string but {type(key)}.")
        if not isinstance(name, str):
            raise ValueError(f"The name is not a string but {type(name)}.")
        if format_type not in _format_types:
            raise ValueError(f"Format type {format_type!r} is not supported.")
        if raw_type not in _struct_map.keys():
            raise ValueError(f"Raw type {raw_type!r} is not supported.")

        if calibration is not None:
            if not isinstance(calibration, list):
                raise ValueError(f"The calibration is not a list but {type(calibration)}.")
            #if any([ c not in (int, float) for c in calibration ]):
            #    raise ValueError(f"The calibration coeff is not a number. {calibration!r}.")

        if enumeration is not None:
            if not isinstance(enumeration, list):
                raise ValueError(f"The enumeration is not a list but {type(enumeration)}")

            for e in enumeration:
                if "string" not in e or not isinstance(e["string"], str):
                    raise ValueError(f"A enumeration is missing a string field. {e!r}")
                if "value" not in e or not isinstance(e["value"], int):
                    raise ValueError(f"A enumeration is missing a value field. {e!r}")

        if calibration is not None and enumeration is not None:
            raise ValueError("Both calibration and enumeration provided")

        if limits is not None:
            pass # TODO

        self.key = key
        self.name = name
        self.format_type = format_type
        self.raw_type = raw_type
        self.units = units
        self.enumeration = enumeration
        self.calibration = calibration


    @property
    def length(self) -> int:
        """ Length of the raw """
        return _lengths[self.raw_type]


    def format(self, calibrated_val: CalibratedType) -> str:
        """ """
        if units := hasattr(self, "units", None):
            return f"{calibrated_val} {units}"
        else:
            return f"{calibrated_val}"


    def parse(self, data: bytes, cursor: int): # -> Tuple[, str]:
        """
        Parses a (name,value) format expression individual field of housekeeping report.
        Return types are:
        (str, int),                       //name-value  pair
        (str, float)                      //name-value  pair
        (str, [(str, bool), ...])         //enum_name:  [name-status pairs]
        (str, [str, ...])                 //enum_name:  [name]   state name list
        """

        if self.length > len(data) - cursor:
            raise ValueError(f"Unexpected end of bytes string. {self.key:=} {cursor:=}")

        # Parse raw value from bytes
        raw_value = struct.unpack(_struct_map[self.raw_type], data[cursor:cursor + _lengths[self.raw_type]])[0]

        if self.calibration:
            # Evaluate calibration function

            # TODO: More generic calibration algorithms
            # cal_type = self.calibration["type"]
            # if cal_type == "polynomial":
            calibrated_val = sum([ coeff * (raw_value**power) for power, coeff in enumerate(self.calibration) ])

        elif self.enumeration:
            # Evaluate enumerations

            calibrated_val = " | ".join([
                str(elem["string"])
                for elem in self.enumeration
                if raw_value & elem.get("mask", 0xFFFFFFFF) == elem["value"]
            ])

        else:
            calibrated_val = raw_value

        # Ensure the returned is in
        calibrated_val = _format_types[self.format_type](calibrated_val)

        return calibrated_val, raw_value


def load_subsystems(schema_path: str) -> Dict[str, Subsystem]:
    """
    Returns:
    """

    with open(schema_path, "r") as f:
        schema = json.load(f)

    subsystems = dict()
    for subsystem in schema["subsystems"]:
        subsystems[subsystem["key"]] = Subsystem(
            key=subsystem["key"],
            name=subsystem["name"],
            fields=[ Field(**field) for field in subsystem["fields"] ]
        )

    return subsystems

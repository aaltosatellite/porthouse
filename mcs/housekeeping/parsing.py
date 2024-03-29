from __future__ import annotations

import os
import json
import struct
from typing import Any, Dict, List, NamedTuple, Union, Optional


_lengths = {"float":4, "uint8":1, "uint16":2, "uint32":4, "uint64":8, "int8":1, "int16":2, "int32":4, }
_struct_map = {"float":"f", "uint8":"B", "uint16":"H", "uint32":"I", "uint64":"L", "int8":"b", "int16":"h", "int32":"i", }
_format_types = {"float":float, "integer":int, "string":str}




# A hefty set of assertions to catch malignant housekeeping spec early.
def check_data_field_correctness(key,name,formatt,raw,enumeration,calibration):
    try:

        assert isinstance(key, str)
        assert isinstance(name, str)
        assert isinstance(formatt, str)
        assert isinstance(raw, str)
        assert  raw in _struct_map.keys()

        kk = struct.unpack(_struct_map[raw], os.urandom(_lengths[raw]))[0]
        assert type(kk) in (int, float)

        assert formatt in _format_types


        if enumeration is not None:

            assert isinstance(enumeration, list)
            # Must have 'string' field
            assert all([ ("string" in e and isinstance(e["string"], str)) for e in enumeration ])
            # Must have 'value' field
            assert all([ ("value" in e and isinstance(e["value"], int)) for e in enumeration ])

            #b4 = [("mask" in e) for e in enum]
            #assert b4 in ([True]*len(enum), [False]*len(enum) )

        elif calibration is not None:
            pass # assert isinstance(calibration, list)
            #assert all([ c in (int, float) for c in calibration ])

    except:
        raise ValueError("Housekeeping specification in housekeeping.json is off-standard and will not work.")




class Subsystem:
    """
    Class to hold housekeeping subsystem structure.
    """

    key: str # Subsystem identifier string
    name: str # Readable name
    fields: List[Field] # List of housekeeping fields

    def __init__(self, key, name, fields):
        self.key = key
        self.name = name
        self.fields = fields

    def get_total_length(self):
        return sum( [k.length for k in self.fields] )

    def parse_blob_for_printing(self, data: bytes) -> Dict[str, Any]:
        """
        OBSOLETE: eps.get_housekeeping() handles this now if verbose=True
        Not used currently, but there was a plan to use this for printing the units as well.
        """
        if not isinstance(data, bytes):
            raise ValueError("'data' is not bytes")
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


    def parse_blob_for_database(self, data: bytes):
        """
        """
        if not isinstance(data, bytes):
            raise ValueError("'data' is not bytes")
        if self.get_total_length() > len(data):
            raise ValueError(f"Insufficient bytes to parse fields determined by the schema file.\n" \
                             f"Expected for {self.key}: {self.get_total_length()}\nGot: {len(data)}")
        parse_output = dict()
        cursor = 0
        for field in self.fields:
            fmtd, raw = field.parse(data, cursor)   # returns the calibrated and raw values
            cursor += field.length
            parse_output[field.key] = fmtd      # better name would be calibrated, not formatted
        return parse_output


    def has_field(self, field_name: str) -> bool:
        """
        Check
        """
        for field in self.subsystems.field:
            if field.name == field_name:
                return True
        return False


    def check_fields(self, field_names: str) -> bool:
        """
        Check
        """
        for field_name in field_names:
            if not self.has_field(field_name):
                raise RuntimeError(f"No such housekeeping field {field_name}")



class Field:
    """
    Class to hold housekeeping field information.
    """

    key: str
    name: str
    format: str
    raw: str
    units: Optional[str]
    enumeration: Optional[int]
    calibration: Optional[int]
    length: int

    def __init__(self, **kwargs):
        self.__dict__.update( kwargs )
        #check_data_field_correctness(key,name,format,raw,enumeration,calibration)
    @property
    def length(self):
        return _lengths[self.raw]


    def parse(self, data: bytes, cursor: int):
        """
        Parses a (name,value) format expression individual field of housekeeping report.
        Return types are:
        (str, int),                       //name-value  pair
        (str, float)                      //name-value  pair
        (str, [(str, bool), ...])         //enum_name:  [name-status pairs]
        (str, [str, ...])                 //enum_name:  [name]   state name list
        """

        if self.length > (len(data) - cursor):
            raise ValueError(f"Unexpected end of bytes string. {self.key:=} {cursor:=}")

        d = data[cursor:cursor+self.length]
        parsed = struct.unpack(_struct_map[self.raw], d)[0]
        parsed_raw = parsed

        if hasattr(self, "calibration"):
            parsed = self.calibrate(parsed)

        if hasattr(self, "enumeration"):
            enum_return = self.parse_enum(parsed)
            return enum_return, parsed_raw

        formatted_value = _format_types[self.format](parsed)
             # calibrated_val,  raw_val
        return formatted_value, parsed_raw


    def calibrate(self, raw: Union[int, float]) -> float:
        """
        """
        if not(hasattr(self, "calibration")):
            return raw

        return raw * self.calibration[0] + self.calibration[1]
        #return sum([ self.calibration[p] * (raw**p) for p in range(len(self.calibration)) ])
        # TODO: More generic calibration algorithms

    def parse_enum(self, raw: int) -> str:
        """
        """
        if not(hasattr(self, "enumeration")):
            return ""
        return " | ".join([
            elem["string"]
            for elem in self.enumeration
            if raw & elem.get("mask", 0xFFFFFFFF) == elem["value"]
        ])






def load_subsystems(schema_path: str) -> Dict[str, Subsystem]:
    """
    Returns:
    """

    with open(schema_path, "r") as f:
        schema = json.load(f)

    hkss = dict()
    for x in schema["subsystems"]:
        subsystem = x
        subsystem_key = subsystem["key"]
        subsystem_name = subsystem["name"]
        fields_dict = subsystem["fields"]
        field_list = []
        for fld in fields_dict:
            field_list.append(Field(**fld))
        hkss[subsystem["key"]] = Subsystem(subsystem_key, subsystem_name, field_list)
    return hkss

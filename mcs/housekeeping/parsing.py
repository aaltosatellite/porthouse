from __future__ import annotations

import os
import json
import struct
from typing import Any, Dict, List, NamedTuple, Union


_lengths = {"float":4, "uint8":1, "uint16":2, "uint32":4, "uint64":8, "int8":1, "int16":2, "int32":4, }
_struct_map = {"float":"f", "uint8":"B", "uint16":"H", "uint32":"I", "uint64":"L", "int8":"b", "int16":"h", "int32":"i", }
_format_types = {"float":float, "integer":int, "string":str}




# A hefty set of assertions to catch malignant housekeeping spec early.
def check_data_field_correctness(key,name,formatt,raw,enum,calibration):
    try:
        assert type(key) == type(name) == type(formatt) == type(raw) == str

        assert  raw in _struct_map

        kk = struct.unpack(_struct_map[raw], os.urandom(_lengths[raw]))[0]
        assert type(kk) in (int, float)

        assert formatt in _format_types


        if enum is not None:

            assert isinstance(enum, list)
            # Must have 'string' field
            assert all([ ("string" in e and isinstance(e["string"], str)) for e in enum ])
            # Must have 'value' field
            assert all([ ("value" in e and isinstance(e["value"], int)) for e in enum ])

            #b4 = [("mask" in e) for e in enum]
            #assert b4 in ([True]*len(enum), [False]*len(enum) )

        elif calibration is not None:
            assert isinstance(calibration, list)
            assert all([ c in (int, float) for c in calibration ])

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
        return sum( [k.leng for k in self.fields] )

    def parse_blob_for_printing(self, data: bytes) -> Dict[str, Any]:
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
            fmtd, raw = field.parse(data, cursor)
            cursor += field.leng
            parse_output[field.key] = fmtd
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
            fmtd, raw = field.parse(data, cursor)
            cursor += field.leng
            parse_output[field.key] = raw
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
    #enum: Optional[]
    #calibration: Optional[]
    length: int

    def __init__(self, key, name, formatt, raw, enum=None, calibration=None):
        check_data_field_correctness(key,name,formatt,raw,enum,calibration)
        self.key = key
        self.name = name
        self.format = formatt
        self.raw = raw
        self.enum = enum
        self.calibration = calibration
        self.leng = _lengths[raw]


    def parse(self, data: bytes, cursor: int):
        """
        Parses a (name,value) format expression individual field of housekeeping report.
        Return types are:
        (str, int),                       //name-value  pair
        (str, float)                      //name-value  pair
        (str, [(str, bool), ...])         //enum_name:  [name-status pairs]
        (str, [str, ...])                 //enum_name:  [name]   state name list
        """

        if self.leng > (len(data) - cursor):
            raise ValueError(f"Unexpected end of bytes string. {self.key:=} {cursor:=}")

        d = data[cursor:cursor+self.leng]
        parsed = struct.unpack(_struct_map[self.raw], d)[0]

        if self.calibration:
            parsed = self.calibrate(parsed)

        if self.enum:
            enum_return = self.parse_enum(parsed)
            return enum_return, parsed

        formatted_value = _format_types[self.format](parsed)
        return formatted_value, formatted_value


    def calibrate(self, raw: Union[int, float]) -> float:
        """
        """
        if self.calibration is None:
            return raw

        return raw * self.calibration[0] + self.calibration[1]
        #return sum([ self.calibration[p] * (raw**p) for p in range(len(self.calibration)) ])
        # TODO: More generic calibration algorithms

    def parse_enum(self, raw: int) -> str:
        """
        """
        if self.enum is None:
            return ""
        return " | ".join([
            elem["string"]
            for elem in self.enum
            if raw & elem.get("mask", 0xFFFFFFFF) == elem["value"]
        ])






def load_subsystems_as_dict(schema_path: str) -> Dict[str, Subsystem]:
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
            ky = fld["key"]
            nm = fld["name"]
            fm = fld["format"]
            rw = fld["raw"]
            enumm = fld.get("enumeration")
            calib = fld.get("calibration")
            if "enumerationn" in fld:
                enumm = fld["enumerationn"]
            field_list.append(Field(ky,nm,fm,rw,enumm,calib))
        hkss[subsystem["key"]] = Subsystem(subsystem_key, subsystem_name, field_list)
    return hkss

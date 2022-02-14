import psycopg2.extensions
import requests
from typing import Union, List


RAW2PSQL = {
    "int8":   "smallint",
    "uint8":  "smallint",
    "int16":  "integer",
    "uint16": "integer",
    "int32":  "integer",
    "uint32": "bigint",
    "float":  "real",
    "double": "double precision"
}

FMT2PSQL = {
    "integer": "bigint",
    "float":   "real",
    "double":  "double precision",
    "binary":  "integer",
    "hex":     "integer",
    "enum":    "character varying",
    "string":  "character varying"
}



def check_table_format_correctness(cursor: psycopg2.extensions.cursor, table_col_ref_list:list, table_name:str) -> bool:
    column_query = """SELECT column_name, data_type FROM  information_schema.columns
                  WHERE table_name = '{}';""".format(table_name)
    cursor.execute(column_query)
    ok = True
    for i in range(len(table_col_ref_list)):
        real = cursor.fetchone()
        if not (real == table_col_ref_list[i]):
            ok = False
    return ok



def check_table_exists(cursor:psycopg2.extensions.cursor, table_name:str) -> bool:
    f = True
    while not (f is None):
        try:
            f = cursor.fetchone()
        except:
            break

    qry = """SELECT column_name FROM  information_schema.columns
                  WHERE table_name = '{}';""".format(table_name)

    cursor.execute(qry)
    f = cursor.fetchone()
    ret = not (f is None)
    while not (f is None):
        try:
            f = cursor.fetchone()
        except:
            break
    return ret

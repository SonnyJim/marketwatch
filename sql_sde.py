#!/usr/bin/env python3

import sqlite3

sde_file = "/home/pi/src/eve/data/sqlite-latest.sqlite"

def sql_sde_connect_to_db():
    conn = sqlite3.connect(sde_file)
    conn.row_factory = lambda cursor, row: row[0]
    if conn == None:
        print ("sql_sde: Error opening database: " +str(sde_file))
    return conn

def get_station_security (conn, station_id):

    c = conn.cursor()
    s = (station_id,)
    c.execute('select security from staStations where stationID is ?', s)
    r = c.fetchone()

    return r

def get_group_id_from_type_id (conn, type_id):
    if type_id == None:
        print ("sql_sde: No type_id specified")
        return "Error"
    if not isinstance(type_id, int):
        print ("sql_sde: type_id was not an int: " + str(type_id))
        return "Error"

    c = conn.cursor()
    t = (type_id,)
    c.execute('select groupID from invTypes where typeID is ?', t)
    r = c.fetchone()
    if r == None:
        print ("sql_sde: couldn't find a groupID for type_id " + str(type_id))
        return "Error"

    return r

def get_region_from_region_id (conn, region_id):
    if region_id == None:
        print ("sql_sde: No region_id specified")
        return "Error"
    if not isinstance(region_id, int):
        print ("sql_sde: region_id was not an int: " + str(region_id))
        return "Error"

    c = conn.cursor()
    t = (region_id,)
    c.execute('select itemName from invNames where itemID is ?', t)
    r = c.fetchone()
    if r == None:
        print ("sql_sde: couldn't find a name for region_id " + str(region_id))
        return "Error"

    return str(r)

def get_name_from_type_id (conn, type_id):
    if type_id == None:
        print ("sql_sde: No type_id specified")
        return "Error"
    if not isinstance(type_id, int):
        print ("sql_sde: type_id was not an int: " + str(type_id))
        return "Error"

    c = conn.cursor()
    t = (type_id,)
    c.execute('select typeName from invTypes where typeID is ?', t)
    r = c.fetchone()
    if r == None:
        print ("sql_sde: couldn't find a name for type_id " + str(type_id))
        return "Error"

    return str(r)

def get_type_id_from_name (conn, name):
    if name == None:
        print ("sql_sde: No name specified")
        return "Error"
    if not isinstance(name, str):
        print ("sql_sde: name was not an string: " + str(name))
        return "Error"

    c = conn.cursor()
    t = (name,)
    c.execute('select typeID from invTypes where typeName is ?', t)
    r = c.fetchone()
    if r == None:
        print ("sql_sde: couldn't find a name for " + str(name))
        return "Error"

    return int(r)


def get_bpid_for_name (conn, name):
    return get_type_id_from_name(conn, str(name) + " Blueprint")

def get_materials_for_bp (conn, type_id):
    if type_id == None:
        print ("sql_sde: No type_id specified")
        return "Error"
    if not isinstance(type_id, int):
        print ("sql_sde: type_id was not an int: " + str(type_id))
        return "Error"

    conn.row_factory = lambda cursor, row: row
    c = conn.cursor()
    t = (type_id,)
    c.execute('SELECT materialTypeID, Quantity FROM industryActivityMaterials WHERE activityID IS 1 AND typeID IS ?', t)
    r = c.fetchall()
    conn.row_factory = lambda cursor, row: row[0]
    if r == None:
        print ("sql_sde: couldn't find a name for type_id " + str(type_id))
        return "Error"

    return r

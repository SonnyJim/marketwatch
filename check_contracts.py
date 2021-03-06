#!/usr/bin/env python3
from esipy import App
from esipy import EsiClient
from esipy import EsiSecurity
from esipy import EsiApp
from esipy.cache import FileCache
import pickle
import requests
import json
import datetime
import pytz
from sql_sde import *

from config import *

from esi_helper import esi_get_station_information
from esi_helper import esi_get_structure_information
from esi_helper import esiChar
from esi_helper import esi_distance_from_station
from esi_helper import esi_get_route
from esi_helper import esi_open_ui_for_contract
from esi_helper import esi_contract_is_still_valid
from esi_helper import esi_get_player_location

cache = FileCache(path="/tmp")

def check_if_expired (expiry_str):
    now = datetime.datetime.now(tz=pytz.utc)
    
    expiry_unaware = datetime.datetime.strptime(expiry_str, '%Y-%m-%dT%H:%M:%SZ')
    expiry = pytz.utc.localize(expiry_unaware)
    
    if expiry < now:
        return True
    else:
        return False


def db_open_contract_db ():
    print ("Opening connection to contract database")
    db_contract_file = "./contracts.db"
    conn = sqlite3.connect(db_contract_file)
    return conn

def contract_still_available (contract_id, expiry):
    if check_if_expired (expiry):
        print ("Contract has expired, removing")
        delete_contract (contract_id)
        return False

    if esi_contract_is_still_valid (contract_id) == False:
        print ("Contract is finished, removing")
        delete_contract (contract_id)
        return False

    return True

def process_row (row):
    contract_id = row[0]
    location_id = row[2]
    buy = row[3]
    sell = row[4]
    price = row[5]
    sell_exchange = row[6]
    items = row[7]
    items_exchange = row[8]
    security = row[9]
    expiry = row[10]
    priority = row[11]
    region_id = row[12]
    buy_profit = row[13]
    sell_profit = row[14]
    volume = row[15]
    dest_system_id = row[16]
    
    print ("Checking contract " + str(contract_id))
    
    if contract_still_available (contract_id, expiry) == False:
        return 0
    
    #Should need to do this as we specify max volume when we query the DB
    #if volume > float(max_volume) and max_volume != 0:
    #    print ("Ignoring contract due to max volume")
    #    return

    #if security < float(min_security):
    #    print ("Ignoring contract due to low security")
    #    return

    #Why is this code here?  Is it because we sometimes don't get the system_id? 
    if dest_system_id is "" or dest_system_id is 0 or dest_system_id is None: 
        if len(str(location_id)) == 8:
            dest_system_id = get_station_system(sde_conn, location_id)
            location_name = get_station_name(sde_conn, location_id)
        else:
            location_info = esi_get_structure_information (location_id, char)
            if location_info is not None:
                dest_system_id = location_info['solar_system_id']
                location_name = location_info['name']
            else:
                location_name = 'Forbidden'
                dest_system_id = 0
        update_contract_system (contract_id, dest_system_id)

    distance = esi_distance_from_station (system_id, dest_system_id, "secure", char)
    

    print (items)

    if len(items_exchange) != 0:
        print ("Exchange items: ")
        print (items_exchange)
    
    print ("Contract ID: " +str(contract_id))
    print ("Priority: " + str(priority))
    if security < 0:
        print ("Security: Nullsec")
    elif security < 0.5:
        print ("Security: Lowsec")
    elif security < 2:
        print ("Security: Highsec")
    else:
        print ("Security: Unknown")
    
    print ("Location: " + location_name + " (" +str(location_id)+")")
    print ("Region: " + str(get_name_from_region_id(sde_conn, region_id)) + "(" + str(region_id) + ")")
    print ("System: " + str(dest_system_id))
    if distance >= 0:
        print ("Jumps: " + str(distance))
    print ("Volume: " + format(volume, ',.2f') +"m3")
    print ("Sell: " + format(sell, ',.2f'))
    print ("Buy: " + format(buy, ',.2f'))
    print ("Contract Price: " + format(price, ',.2f'))

    print ("Buy Profit: " + format(buy_profit, ',.2f'))

    print ("Sell Profit: " + format(sell_profit, ',.2f'))
    
    if distance >= 0:
        print ("Profit/Jump: " + format(sell_profit/distance, ',.2f'))
    esi_open_ui_for_contract (contract_id, char)
    new_priority = input ("Enter in new priority: ")
    if new_priority.isdigit():
        if int(new_priority) <= 5 and int(new_priority) >= 0:
            update_contract_priority (contract_id, new_priority)
        else:
            print ("Didn't recognise new priority: " + str(new_priority))
    elif new_priority == "d":
        delete_contract (contract_id)
    elif new_priority == "g":
        get_contract_authed (contract_id)
    elif new_priority == "q":
        return -2
    elif new_priority == "r":
        print ("Restarting")
        return -1
    elif new_priority == "R":
        print ("Checking route")
        return dest_system_id

    return 0



def delete_contract (contract_id):
    print ("Removing " + str(contract_id) + " from database")
    sql = "DELETE FROM contracts WHERE contract_id = " + str(contract_id)
    c = conn.cursor ()
    c.execute (sql)
    conn.commit()

def update_contract_priority (contract_id, priority):
    sql = "UPDATE contracts SET priority = " + str(priority) + " WHERE contract_id = " + str(contract_id)
    c = conn.cursor ()
    c.execute (sql)
    conn.commit()

def update_contract_system (contract_id, system_id):
    sql = "UPDATE contracts SET system_id = " + str(system_id) + " WHERE contract_id = " + str(contract_id)
    c = conn.cursor ()
    c.execute (sql)
    conn.commit()

def prune_contracts (rows):
    print ("Pruning contracts")
    contracts_pruned = 0
    for row in rows:
        contract_id = row[0]
        expiry = row[10]
        print ("Checking contract " + str(contract_id))
        if contract_still_available (contract_id, expiry) == False:
            contracts_pruned += 1

    print ("Pruned " +str(contracts_pruned)+" contracts from database")
    
    

def check_contracts (rows):
    if len(rows) == 0:
        print ("No contracts found")
        return 0
    for row in rows:
        r = process_row (row)
        if r != 0:
            return r

def db_get_contracts (conn, min_security, max_volume, region, systems):
    print ("Fetching contracts from database")
    sql = "SELECT * FROM contracts WHERE security >= " + str(min_security)
    sql += " and profit_buy > 0"
    
    if max_volume is not "":
        sql += " and volume <= " + str(max_volume)
    
    if region is not "":
        sql += " and region_id is " + str(region)
    elif systems is not "":
        if isinstance(systems,list):
            sql += " and ("
            for system in systems:
                sql += "system_id='" + str(system) + "'"
                if system != systems[-1]:
                    sql += " OR "
            sql += ")"

        else:
            sql += " and system_id is " + str(systems)


    sql += " ORDER BY priority DESC, profit_buy DESC"
    #sql = "SELECT * FROM contracts WHERE security >= " + str(min_security) + " and volume < " + str(max_volume) + " ORDER BY profit_sell DESC"
    print (sql)
    c = conn.cursor()
    c.execute(sql)
    rows = c.fetchall()
    return rows
#    for row in rows:
#    if process_row (row) == -1:
#            return


def get_player_location (char):
    location = esi_get_player_location (char);
    return location.solar_system_id

def main():
    global conn
    global sde_conn
    global min_security
    global max_volume
    global char
    global running
    char = esiChar("tokens.txt")
    
    conn = db_open_contract_db ()
    sde_conn = sql_sde_connect_to_db ()
    running = True
    prune = False
    contracts_return = 0
    while running:
       
        if prune:
            rows = db_get_contracts (conn, -1, 99999999999, "", "")
            prune_contracts (rows)
            exit ()

        min_security = input ("Minimum security: ")
        if min_security == "":
            min_security = -1
        max_volume = input ("Max volume: ")
        
        if contracts_return > 0:
            systems = esi_get_route (system_id, contracts_return, "secure", char)
            print (isinstance(systems, list))

            rows = db_get_contracts (conn, min_security, max_volume, "", systems)
        else:
            region = input ("Limit to region: ")
            if region is "":
                system = input ("Limit to system: ")
                if system == "c":
                    system = get_player_location (char)
                rows = db_get_contracts (conn, min_security, max_volume, region, system)
        contracts_return = check_contracts (rows)
        if contracts_return == -2:
            running = False

    print ("Exiting....")

    
if __name__ == "__main__":
    main()

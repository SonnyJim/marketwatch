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
from esi_helper import esi_open_ui_for_contract

cache = FileCache(path="/tmp")

def db_open_contract_db ():
    print ("Opening connection to contract database")

    db_contract_file = "./contracts.db"
    conn = sqlite3.connect(db_contract_file)
    return conn

def get_structure_information (structure_id):
    op = app.op['universe_structures_structure_id'](structure_id=structure_id)
    r = client.request(op)

    if r.status != 200:
        print ("distance: Couldn't get solar system for structure: error " + str(r.status))
        return 0, 'Unknown'
    return r.data['solar_system_id'], r.data['name']


def get_station_information (station_id):
    op = app.op['universe_stations_station_id'](station_id=station_id)
    r = client.request(op)

    if r.status != 200:
        print ("distance: Couldn't get solar system for station: error " + str(r.status))
        return 0, 'Unknown'
    return r.data['system_id'],r.data['name']


def distance_from_station (origin, destination):
    #print ("distance: Calculating route from " + str(origin) + " to " + str(destination))
    op = app.op['get_route_origin_destination'](origin=origin, destination=destination)
    r = client.request(op)

    if r.status != 200:
        print ("distance: Couldn't get distance from station: error " + str(r.status))
        return -1
    distance = len(r.data)
    return distance


#db_add_contract (contract_id, location_id, buy, sell, price, sell_exchange, items, items_exchange, security, expiry, priority, region_id)
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
    
    if security < float(min_security):
        print ("Ignoring contract due to low security")
        return
    
    if volume > float(max_volume) and max_volume != 0:
        print ("Ignoring contract to do max volume")
        return

    if len(str(location_id)) == 8:
        location_info = esi_get_station_information (location_id, char)
    else:
        location_info = esi_get_structure_information (location_id, char)
        
    dest_system_id = location_info['solar_system_id']
    location_name = location_info['name']

    distance = esi_distance_from_station (system_id, dest_system_id, "secure", char)
    
    #if priority == 0:
    #    print ("Not worth my time, mate")
    #    return

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
        update_contract_priority (contract_id, new_priority)
    elif new_priority == "d":
        delete_contract (contract_id)
    elif new_priority == "g":
        get_contract_authed (contract_id)
    elif new_priority == "q":
        exit ()


def delete_contract (contract_id):
    print ("Removing " + str(contract_id) + " form database")
    sql = "DELETE FROM contracts WHERE contract_id = " + str(contract_id)
    c = conn.cursor ()
    c.execute (sql)
    conn.commit()

def update_contract_priority (contract_id, priority):
    sql = "UPDATE contracts SET priority = " + str(priority) + " WHERE contract_id = " + str(contract_id)
    c = conn.cursor ()
    c.execute (sql)
    conn.commit()

def db_check_contracts (conn, order_type):
    #sql = "SELECT * FROM contracts WHERE " + order_type + " > price ORDER BY priority DESC"
    #sql = "SELECT * FROM contracts price ORDER BY priority DESC, profit_buy DESC"
    sql = "SELECT * FROM contracts price ORDER BY priority DESC, profit_buy DESC"
    c = conn.cursor()
    c.execute(sql)
    rows = c.fetchall()
    for row in rows:
        process_row (row)

def do_security():
    global client
    global app
    print ("security: Authenticating")

    #Retrieve the tokens from the film
    with open("tokens.txt", "rb") as fp:
        tokens_file = pickle.load(fp)
    fp.close()

    esi_app = EsiApp(cache=cache, cache_time=0, headers=headers)
    app = esi_app.get_latest_swagger

    security = EsiSecurity(
            redirect_uri=redirect_uri,
            client_id=client_id,
            secret_key=secret_key,
            headers=headers
            )

    client = EsiClient(
            retry_requests=True,
            headers=headers,
            security=security
            )

    security.update_token({
        'access_token': '',
        'expires_in': -1,
        'refresh_token': tokens_file['refresh_token']
        })

    tokens = security.refresh()
    api_info = security.verify()
    print ("security: Authenticated for " + str(api_info['Scopes']))

def open_ui_for_contract (contract_id):
    #print ("ui: Opening UI for item_id " + str(contract_id))
    op = app.op['post_ui_openwindow_contract'](contract_id=contract_id)
    ui = client.request(op)

    #if (ui.status_code != 204):
    #    print ("ui: Error opening window: error "+ str(ui.status_code))
def main():
    global conn
    global sde_conn
    global min_security
    global max_volume
    global char
    #do_security ()
    char = esiChar("tokens.txt")
    min_security = input ("Minimum security: ")
    if min_security == "":
        min_security = -2
    max_volume = input ("Max volume: ")
    if max_volume == "":
        max_volume = 0



    conn = db_open_contract_db ()
    sde_conn = sql_sde_connect_to_db ()
    #db_check_contracts (conn, 'buy')
    db_check_contracts (conn, 'sell')
    #contract_id = input ("Enter in contract id: ")
    print ("Exiting....")

    
if __name__ == "__main__":
    main()

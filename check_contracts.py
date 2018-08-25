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

cache = FileCache(path="/tmp")

def db_open_contract_db ():
    print ("Opening connection to contract database")

    db_contract_file = "./contracts.db"
    conn = sqlite3.connect(db_contract_file)
    return conn

def get_structure_solar_system_id (structure_id):
    op = app.op['universe_structures_structure_id'](structure_id=structure_id)
    r = client.request(op)

    if r.status != 200:
        print ("distance: Couldn't get solar system for structure: error " + str(r.status))
        return 0
    print (r.data)
    return r.data['solar_system_id']


def get_station_solar_system_id (station_id):
    op = app.op['universe_stations_station_id'](station_id=station_id)
    r = client.request(op)

    if r.status != 200:
        print ("distance: Couldn't get solar system for station: error " + str(r.status))
        return 0
    return r.data['system_id']


def distance_from_station (origin, destination):
    #print ("distance: Calculating route from " + str(origin) + " to " + str(destination))
    op = app.op['get_route_origin_destination'](origin=origin, destination=destination)
    r = client.request(op)

    if r.status != 200:
        print ("distance: Couldn't get distance from station: error " + str(r.status))
        return -1
    distance = len(r.data)
    return distance


def process_row (row):
    contract_id = row[0]
    location_id = row[2]
    buy = row[3]
    sell = row[4]
    price = row[5]
    items = row[6]
    security = row[7]
    expiry = row[8]
    priority = row[9]
    
    if len(str(location_id)) == 8:
        dest_system_id = get_station_solar_system_id (location_id)
    else:
        dest_system_id = get_structure_solar_system_id (location_id)

    distance = distance_from_station (system_id, dest_system_id)
    
    if distance > 0:
        distance = distance * 2
    #if priority == 0:
    #    print ("Not worth my time, mate")
    #    return

    print (items)
    
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
    
    if distance >= 0:
        print ("Jumps: " + str(distance))
    print ("Sell: " + format(sell, ',.2f'))
    print ("Buy: " + format(buy, ',.2f'))
    print ("Contract Price: " + format(price, ',.2f'))

    buy_profit = buy - price
    sell_profit = sell - price
    print ("Buy Profit: " + format(buy_profit, ',.2f'))

    print ("Sell Profit: " + format(sell_profit, ',.2f'))
    
    if distance >= 0:
        print ("Profit/Jump: " + format(sell_profit/distance, ',.2f'))
    open_ui_for_contract (contract_id)
    new_priority = input ("Enter in new priority: ")
    if new_priority != "":
        update_contract_priority (contract_id, new_priority)
    elif new_priority == "q":
        exit ()


def update_contract_priority (contract_id, priority):
    sql = "UPDATE contracts SET priority = " + str(priority) + " WHERE contract_id = " + str(contract_id)
    c = conn.cursor ()
    c.execute (sql)
    conn.commit()

def db_check_contracts (conn, order_type):
    sql = "SELECT * FROM contracts WHERE " + order_type + " > price ORDER BY priority DESC"
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
    print ("ui: Opening UI for item_id " + str(contract_id))
    op = app.op['post_ui_openwindow_contract'](contract_id=contract_id)
    ui = client.request(op)

    #if (ui.status_code != 204):
    #    print ("ui: Error opening window: error "+ str(ui.status_code))
def main():
    global conn
    do_security ()
    #open_ui_for_contract (135920680)
    #input()
    conn = db_open_contract_db ()
    #db_check_contracts (conn, 'buy')
    db_check_contracts (conn, 'sell')
    #contract_id = input ("Enter in contract id: ")
    print ("Exiting....")

    
if __name__ == "__main__":
    main()

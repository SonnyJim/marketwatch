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
    
    if priority == 0:
        print ("Not worth my time, mate")
        return

    print (items)
    
    print ("Priority: " + str(priority))
    if security < 0:
        print ("Security: Nullsec")
    elif security < 0.5:
        print ("Security: Lowsec")
    elif security < 2:
        print ("Security: Highsec")
    else:
        print ("Security: Unknown")

    print ("Sell: " + format(sell, ',.2f'))
    print ("Buy: " + format(buy, ',.2f'))
    print ("Contract Price: " + format(price, ',.2f'))

    profit = buy - price
    print ("Buy Profit: " + format(profit, ',.2f'))

    profit = sell - price
    print ("Sell Profit: " + format(profit, ',.2f'))

    open_ui_for_contract (contract_id)
    input ()

def db_check_contracts (conn, order_type):
    sql = "SELECT * FROM contracts WHERE " + order_type + " > price"
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
    do_security ()
    conn = db_open_contract_db ()
    #db_check_contracts (conn, 'buy')
    db_check_contracts (conn, 'sell')
    #contract_id = input ("Enter in contract id: ")
    #open_ui_for_contract (contract_id)
    print ("Exiting....")

    
if __name__ == "__main__":
    main()

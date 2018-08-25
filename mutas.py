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

#FIXME 
#Get's confused with BPCs, seems to be comparing it against BPOs
#Adds in the value of rigs fitted to ships
#Damaged crystals are unsellable but still counted in the valuation
#Calculate cost of 'you will pay' items
#Generate a report rather than opening the UI each time
#db_add_contract will probably fail on items with a ' in the name like auggy drones

def db_open_contract_db ():
    if verbose:
        print ("Opening connection to contract database")

    db_contract_file = "./contracts.db"
    conn = sqlite3.connect(db_contract_file)
    c = conn.cursor()
    
    sql = "CREATE TABLE IF NOT EXISTS contracts (contract_id INTEGER PRIMARY_KEY, checked BOOLEAN, \
        location_id INTEGER, buy FLOAT, sell FLOAT, price FLOAT, items CHAR(2048), security FLOAT, expiry CHAR(128), priority INTEGER)" 
    c.execute(sql)
    conn.commit ()
    return conn


def db_add_contract (contract_id, location_id, buy, sell, price, items, security, expiry, priority):
    if verbose:
        print ("Adding contract id " + str(contract_id) + " to database")

    c = db_contract.cursor()
    try:
        c.execute('INSERT INTO contracts (contract_id, checked, location_id, buy, sell, price, items, security, expiry, priority) \
                VALUES ({ci}, "TRUE", {li}, {buy}, {sell}, {price}, "{items}", {security}, "{expiry}", {priority})'.\
                            format(ci=contract_id, li=location_id, buy=buy, sell=sell, price=price, items=items, \
                            security=security, expiry=expiry, priority=priority))
    except sqlite3.IntegrityError:
            print('ERROR: ID already exists in PRIMARY KEY column {}'.format(id_column))
    db_contract.commit()

def db_check_contract (contract_id):
    if verbose:
        print ("Checking to see if we have contract " + str(contract_id) + " in the database")

    sql = "SELECT checked FROM contracts WHERE contract_id=" + str(contract_id)
    c = db_contract.cursor()
    c.execute(sql)
    r = c.fetchone()
    if r is None:
        return False
    else:
        return True

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

def fetch_appraisal (text):
    if len(text) == 0:
        if verbose:
            print ("Error:  appraisal text empty")
        return None
    if verbose:
        print ("Fetching appraisal")


    market = "jita"
    #url = "https://evepraisal.com/appraisal.json?market=" + market + "&raw_textarea=" + text + "&persist=no"
    url = "https://evepraisal.com/appraisal.json?market=" + market + "&persist=no"
    if verbose:
        print (text)
    r = requests.post (url, headers=headers, data=text)
    
    if r.status_code !=200:
        print ("Error fetching appraisal: " + str(r.status_code))
        print (url)
        input ()
        #exit (1)

    appraisal = json.loads(r.text)
    return appraisal

def create_appraisal (contract_items):
    if verbose:
        print ("Creating appraisal list")
    appraisal_text = ""
    for contract_item in contract_items:
        # Seller is asking for item in return
        if contract_item['is_included'] is False:
            continue
        if 'is_blueprint_copy' in contract_item:
            continue
        
        #Fetch the name, as evepraisal seems to work that way
        name = get_name_from_type_id (db_sde, contract_item['type_id'])
        if "Abyssal" in name:
            continue
        #if 'is_singleton' in contract_item:
        #    print ("Error: item is fitted to ship? " + get_name_from_type_id (conn, contract_item['type_id']))
        #    continue
        #print (get_name_from_type_id(conn, contract_item['type_id']) + " x " + str(contract_item['quantity']))
        appraisal_text += name
        appraisal_text += " " + str(contract_item['quantity'])
        appraisal_text += "\r\n"

    return appraisal_text

def get_appraisal (contract_items):
    appraisal_text = create_appraisal (contract_items)
    appraisal = fetch_appraisal (appraisal_text)
    return appraisal

def get_contract_items (contract_id):
    if verbose:
        print ("Getting items for contract_id: " + str(contract_id))
    items = []
    url = "https://esi.evetech.net/latest/contracts/public/items/" + str(contract_id) + "/?datasource=tranquility&page=1"
    r = requests.get (url, headers=headers)
    if r.status_code != 200:
        print ("get_contract_items: Error " + str(r.status_code))
        return
        #exit (1)
    
    if int(r.headers['X-Pages']) > 1:
        print ("Found more than one page of results, we should be looping right now")
        exit (1)

    contract_items = json.loads(r.text)

    return contract_items

    #for contract_item in contract_items:
    #    print (contract_item)
    #    items.append (contract_item['type_id'])
    #    check_contract_items (contract_item['type_id'])

def check_if_expired (expiry_str):
    now = datetime.datetime.now(tz=pytz.utc)
    
    #Convert string into datetime object
    #2018-08-24T06:20:02Z

    expiry_unaware = datetime.datetime.strptime(expiry_str, '%Y-%m-%dT%H:%M:%SZ')
    expiry = pytz.utc.localize(expiry_unaware)
    
    if expiry < now:
        return True
    else:
        return False

def extract_contract_ids (contract_type, contracts):
    global contract_count
    print ("Extracting contract_ids for type: " + str(contract_type))
    contract_ids = []
    prices = []
    for contract in contracts:
        if contract['type'] == contract_type and not check_if_expired (contract['date_expired']):
            contract_ids.append (contract['contract_id'])
            prices.append (contract['price'])
   
    contract_count = len(contract_ids)
    print ("Found " + str(contract_count) + " contracts to search")
    return contract_ids, prices

def get_contract (contract_id, contracts):
    for contract in contracts:
        if contract['contract_id'] == contract_id:
            return contract
    
    print ("get_contract: Error could not find contract_id: " + str(contract_id))
    exit (1)

def get_contracts_for_region (region_id):
    print ("Fetching public contracts for reqion: " + str(region_id))
    page = 1
    url = "https://esi.evetech.net/latest/contracts/public/" + str(region_id) + "/?datasource=tranquility&page=" + str(page)
    r = requests.get (url, headers=headers)
    if r.status_code != 200:
        print ("get_contracts_for_region: Error " + str(r.status_code))
        exit (1)

    if int(r.headers['X-Pages']) > 1:
        print ("Found more than one page of results, we should be looping right now")
        exit (1)


    contracts = json.loads(r.text)
    return contracts

def get_contract_location (contract_id, contracts):
    for contract in contracts:
        if contract['contract_id'] == contract_id:
            return contract['start_location_id']
    return 0

def make_stars (length):
    text = ""
    i = 0
    while i < length:
        text += "*"
        i += 1
    return text

def check_region (region_id):
    contracts = get_contracts_for_region (region_id)
    contract_ids = extract_contract_ids ("item_exchange", contracts)
    
    #Unpack the tuple - FIXME
    prices = contract_ids[1]
    contract_ids = contract_ids[0]
    contracts_checked = 0
    for contract_id in contract_ids:
        contracts_checked += 1
        
        label = (str(contracts_checked) + "/" + str(contract_count) + " Contract ID: " + str(contract_id))
        stars = make_stars (len(label))
        if verbose:
            print ("")
            print (stars)
        print (label)
        if verbose:
            print (stars)
        
        if db_check_contract (contract_id) is True:
            if verbose:
                print ("Contract ID " + str(contract_id) + " is already in the database")
            continue
        try: 
            contract = get_contract (contract_id, contracts)
            expiry = contract['date_expired']
        except:
            expiry = "UNKNOWN"

        contract_items = get_contract_items (contract_id)
        
        
        if contract_items == None:
            print ("Error:  Couldn't find any contract items")
            continue

        price = prices[contract_ids.index(contract_id)]
        items = create_appraisal (contract_items)
        appraisal = fetch_appraisal (items)
        #appraisal = get_appraisal (contract_items)

        
        if appraisal is None:
            if verbose:
                print ("Nothing to appraise")
            db_add_contract (contract_id, 0, 0, 0, 0, "BLUEPRINT COPIES", 2, "UNKNOWN", 6)
            continue
        try:
            buy = appraisal['appraisal']['totals']['buy']
            sell = appraisal['appraisal']['totals']['sell']
        except:
            buy = 0
            sell = 0

        target = buy

        #try:
        #    location_id = get_contract_location (contract_id, contracts)
        #except:
        #    print ("Error fetching location_id for contract " + str(contract_id))
        #    print (get_contract (contract_id))
        #    location_id = 0
        location_id = contract['start_location_id']

        try:
            security = get_station_security (db_sde, location_id)
        except:
            print ("Error fetching security for location " + str(location_id))
            security = 2

        if verbose:
            print ("Sell: " + format(sell, ',.2f'))
            print ("Buy: " + format(buy, ',.2f'))
            print ("Contract Price: " + format(price, ',.2f'))
        
        profit = target - price
        
        if profit > 50000000:
            priority = 5
        elif profit > 25000000:
            priority = 4
        elif profit > 10000000:
            priority = 3
        elif profit > 5000000:
            priority = 2
        elif profit > 1000000:
            priority = 1
        else:
            priority = 0

        db_add_contract (contract_id, location_id, buy, sell, price, items, security, expiry, priority)
        if target > price:
            print ("Sell: " + format(sell, ',.2f'))
            print ("Buy: " + format(buy, ',.2f'))
            print ("Contract Price: " + format(price, ',.2f'))
            profit = target - price
            print ("Awooga Profit " + format(profit, ',.2f'))
            #open_ui_for_contract (contract_id)
            #input ()

def main():
    global contracts
    global db_sde #SDE connection
    global db_contract
    global verbose

    print ("Startin' muta watch")
    print ("10000036 Devoid")
    print ("10000030 Heimatar")
    print ("10000042 Metropolis")
    print ("10000002 The Forge")
    print ("10000037 Everyshore")
    print ("10000032 Sinq Laison")
    print ("10000033 The Citadel")
    print ("10000043 Domain")
    print ("10000064 Essence")
    
    regions = (10000036, 10000030, 10000042, 10000002, 10000037, 10000032, 10000033, 10000043, 10000064)
    verbose = False
    #region_id = input ("Enter in region id: ")
    #region_id = 10000016
    db_sde = sql_sde_connect_to_db ()
    db_contract = db_open_contract_db ()
    do_security ()
    
    for region_id in regions:
        check_region (region_id)
    print ("Exiting....")

    
if __name__ == "__main__":
    main()

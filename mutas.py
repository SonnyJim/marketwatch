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
import logging
from sql_sde import *

from config import *

cache = FileCache(path="/tmp")

from esi_helper import esiChar
from esi_helper import esi_get_structure_information
from esi_helper import esi_get_status

from time import sleep

#FIXME 
#Adds in the value of rigs fitted to ships
#Damaged crystals are unsellable but still counted in the valuation
#Some weird encoding problems
#Log contract_ids we couldn't complete for further inspection
#Log 403 structures so we aren't wasting time checking them again
#Reduce the amount of calls when checking for rigs
#Prune expired or completed contracts


def db_open_contract_db ():
    if verbose:
        print ("Opening connection to contract database")

    db_contract_file = "./contracts.db"
    conn = sqlite3.connect(db_contract_file)
    c = conn.cursor()
    
    sql = "CREATE TABLE IF NOT EXISTS contracts (contract_id INTEGER PRIMARY_KEY, checked BOOLEAN, \
        location_id INTEGER, buy FLOAT, sell FLOAT, price FLOAT, items_exchange_cost FLOAT, items VARCHAR(8192), \
        items_exchange VARCHAR(8192), security FLOAT, \
        expiry CHAR(128), priority INTEGER, region_id INTEGER, \
        profit_buy FLOAT, profit_sell FLOAT, volume INTEGER, items_typeids TEXT, items_exchange_typeids TEXT, system_id INT, distance INT \
        )" 
    c.execute(sql)
    conn.commit ()

    sql = "CREATE TABLE IF NOT EXISTS locations (location_id INT, system_id INT, region_id INT, name TEXT, dockable BOOLEAN, distance INT)"
    c.execute(sql)
    conn.commit()
    return conn


def db_add_contract (contract_id, location_id, buy, sell, price, items_exchange_cost, \
        items, items_exchange, security, expiry, priority, region_id, \
        profit_buy, profit_sell, volume, system_id):
    if verbose:
        print ("Adding contract id " + str(contract_id) + " to database")

    c = db_contract.cursor()
    try:
        args = (contract_id, "FALSE", location_id, buy, sell, price, items_exchange_cost, items, \
                items_exchange, security, expiry, priority, region_id, profit_buy, profit_sell, volume, system_id)
        c.execute('INSERT INTO contracts (contract_id, checked, location_id, buy, sell, price, items_exchange_cost, items, \
                items_exchange, security, expiry, priority, region_id, profit_buy, profit_sell, volume, system_id) \
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', args)
    except sqlite3.IntegrityError:
        print('Error: ID already exists in PRIMARY KEY column {}'.format(id_column))
    except sqlite3.OperationalError as e:
                    print('[-] Sqlite operational error: {}'.format(e))
                    exit ()
    db_contract.commit()

def db_get_contract_ids (region_id):
    if verbose:
        print ("Fetching the list of already checked contract ids from the database")

    sql = "SELECT contract_id FROM contracts WHERE region_id is " + str(region_id)
    db_contract.row_factory = lambda cursor, row: row[0]
    c = db_contract.cursor()
    c.execute(sql)
    r = c.fetchall()
    db_contract.row_factory = lambda cursor, row: row
    return r

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

def get_structure_information (location_id):

    sql = "SELECT security, system_id, dcckable FROM structures WHERE location_id IS " + str(location_id)
    c = db_contract.cursor()
    c.execute(sql)
    r = c.fetchone()
    if r == None:
        info = esi_get_structure_information (location_id, char)
        if info == -1:
            #Structure is inaccesible?
            security = -1
            system_id = -1
            dockable = False
        else:
            system_id = info['solar_system_id']
            security = get_system_security (db_sde, system_id)
            dockable = True
        c.exe
    elif r[3] is True:
        security = r[0]
        system_id = r[1]

    return security,system_id
        #Fetch it from the ESI
def fetch_appraisal (text, items):
    if len(text) == 0:
        if verbose:
            print ("Error:  appraisal text empty")
        return None
    if verbose:
        print ("Fetching appraisal")


    market = "jita"
    url = "https://evepraisal.com/appraisal.json?market=" + market + "&persist=no"
    if verbose:
        print (text)
    r = requests.post (url, headers=headers, data=text)
    
    if r.status_code !=200:
        print ("Error fetching appraisal: " + str(r.status_code))
        return -1
        #FIXME Log error
        #Probably want to return None then check on the other end

    appraisal = json.loads(r.text)
    return appraisal

def create_appraisal (contract_items, is_included):
    if verbose:
        print ("Creating appraisal list ")
    appraisal_text = ""
    for contract_item in contract_items:
        #if 'raw_quantity' in contract_item:
        #    if contract_item['raw_quantity'] == -1:
        #        print ("Item is singleton, not including: " + str(contract_item))
        #        continue

        # False if Seller is asking for item in return
        if contract_item['is_included'] is is_included:
            continue
        # Ignore BPCs for now
        if 'is_blueprint_copy' in contract_item:
            continue
        
        #Fetch the name, as evepraisal seems to work that way
        name = get_name_from_type_id (db_sde, contract_item['type_id'])
        if "Abyssal" in name:
            continue

        appraisal_text += name
        appraisal_text += " " + str(contract_item['quantity'])
        appraisal_text += "\r\n"
        #FIXME Massive bodge because somewhere in the SDE there's a wrong backtick
        appraisal_text = appraisal_text.replace(u"\u2018", "'").replace(u"\u2019", "'")
        appraisal_text = appraisal_text.replace(u"\u2013", "-")
    return appraisal_text

def get_rig_groupids():
    sql = "select groupID from invGroups where groupName like '%Rig %' and groupName not like '%Structure%'"
    c = db_sde.cursor()
    c.execute(sql)
    r = c.fetchall()
    print ("Ignoring group IDs: ")
    print (r)
    return r
 
def check_contract_items_for_marketable_items (contract_items):
    if verbose:
        print ("Checking contract items for stuff we can sell via the market")
    
    contract_items_minus_unmarketables = []

    if contract_items is None:
        return None
    
    for item in contract_items:
        if check_if_type_id_is_marketable (db_sde, item['type_id']) is True:
            contract_items_minus_unmarketables.append(item)
        else:
            print ("Item is not marketable: " + str(item))

    return contract_items_minus_unmarketables

def check_contract_items_for_fitted_rigs (contract_items):
    if verbose:
        print ("Checking contract items for fitted rigs")
    contract_items_minus_rigs = []
    if contract_items is None:
        return None

    for item in contract_items:
        groupid = get_group_id_from_type_id (db_sde, item['type_id'])
        if groupid in rig_groupids:
            print (item)
            print ("item type " + str(item['type_id']) + " is a rig in group " + str(groupid))
            print ("It's record id is " + str(item['record_id']))
            #input ()
        else:
            contract_items_minus_rigs.append (item)

    return contract_items_minus_rigs

def check_if_expired (expiry_str):
    now = datetime.datetime.now(tz=pytz.utc)
    
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

def get_contract_items (contract_id):
    if verbose:
        print ("Getting items for contract_id: " + str(contract_id))
    items = []
    page = 0
    fetched_all_pages = False
    
    while not fetched_all_pages:
        page +=1
        url = "https://esi.evetech.net/latest/contracts/public/items/" + str(contract_id) + "/?datasource=tranquility&page=" + str(page)
        r = requests.get (url, headers=headers)
        if r.status_code != 200:
            print ("get_contract_items: Error " + str(r.status_code))
            return
        if page is 1:
            contract_items = json.loads(r.text)
        else:
            new_page = json.loads(r.text)
            contract_items += new_page
        if int(r.headers['X-Pages']) <= page:
            fetched_all_pages = True

    contract_items = json.loads(r.text)

    return contract_items


def get_contracts_for_region (region_id):
    print ("Fetching public contracts for reqion: " + get_name_from_region_id (db_sde, region_id))

    page = 0
    fetched_all_pages = False

    while not fetched_all_pages:
        page += 1
        print ("Fetching page " + str(page))
        url = "https://esi.evetech.net/latest/contracts/public/" + str(region_id) + "/?datasource=tranquility&page=" + str(page)
        r = requests.get (url, headers=headers)
        if r.status_code != 200:
            print ("get_contracts_for_region: Error " + str(r.status_code))
            if page == 1:
                return -1
            else:
                return contracts
        
        if page is 1:
            contracts = json.loads(r.text)
        else:
            new_page = json.loads(r.text)
            contracts += new_page
        if int(r.headers['X-Pages']) <= page:
            fetched_all_pages = True

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
    if contracts == -1:
        print ("Error fetching contracts for region, skipping")
        return
    contract_ids = extract_contract_ids ("item_exchange", contracts)
    
    #Unpack the tuple - FIXME
    prices = contract_ids[1]
    contract_ids = contract_ids[0]
    contracts_checked = 0
    region_contract_ids = db_get_contract_ids (region_id)

    for contract_id in contract_ids:
        contracts_checked += 1
            
        label = (str(contracts_checked) + "/" + str(contract_count) + " Contract ID: " + str(contract_id))

        if verbose:
            stars = make_stars (len(label))
            print ("")
            print (stars)
            print (label)
            print (stars)
        elif contracts_checked % 100 == 0:
            print (label)
        
        #Check to see if we can skip the contract for whatever reason
        if contract_id in region_contract_ids:
            if verbose:
                print ("Contract ID " + str(contract_id) + " is already in the database")
            continue

        if contract_id in broken_contracts:
            print ("Contract is broken: " + str(contract_id))
            continue

        try: 
            contract = get_contract (contract_id, contracts)
            expiry = str(contract['date_expired'])
        except:
            expiry = "UNKNOWN"
        
        location_id = contract['start_location_id']
        if location_id in forbidden_structures:
            print ("Skipping contract due to forbidden structure: " + str(location_id))
            continue

        #Start checking the items in the contract       
        volume = contract['volume']
        contract_items = get_contract_items (contract_id)
        #Strip out any items that are rigs
        if dont_count_rigs:
            contract_items = check_contract_items_for_fitted_rigs (contract_items)
        #Strip out any items we can't sell via the market
        contract_items = check_contract_items_for_marketable_items (contract_items)
        if contract_items == None:
            print ("Error:  Couldn't find any contract items")
            broken_contracts.append (contract_id)
            continue

        #check_contract_items_for_fitted_rigs (contract_items)
        price = prices[contract_ids.index(contract_id)]
        # Fetch the text names for the items and split them up into items and items wanted in exchange
        items = create_appraisal (contract_items, False)
        items_exchange = create_appraisal (contract_items, True)

        appraisal = fetch_appraisal (items, contract_items)
        appraisal_exchange = fetch_appraisal (items_exchange, contract_items)
        
        if appraisal is None:
            if verbose:
                print ("Nothing to appraise")
            db_add_contract (contract_id, 0, 0, 0, 0, 0, items, "BLUEPRINT COPIES", 2, expiry, -1, region_id, 0, 0, 0,0)
            continue

        if appraisal is -1 or appraisal_exchange is -1:
            logging.warning ("Couldn't create the appraisal for contract " + str(contract_id))
            broken_contracts.append (contract_id)
            continue
        
        try:
            sell_exchange = appraisal_exchange['appraisal']['totals']['sell']
        except:
            logging.warning ("Couldn't get the appraisal totals for contract " + str(contract_id))
            sell_exchange = 0
        


        try:
            buy = appraisal['appraisal']['totals']['buy']
            sell = appraisal['appraisal']['totals']['sell']
        except:
            logging.warning ("Couldn't get the appraisal totals for contract " + str(contract_id))
            buy = 0
            sell = 0

        target = buy
        
        try:
            if len(str(location_id)) == 8:
                security = get_station_security (db_sde, location_id)
                system_id = get_station_system (db_sde, location_id)
            else:
                info = esi_get_structure_information (location_id, char)
                system_id = info['solar_system_id']
                security = get_system_security (db_sde, system_id)

        except:
            forbidden_structures.append (location_id)
            error = "Error fetching security for location " + str(location_id)
            print (error)
            logging.warning (error)
            continue

        if verbose:
            print ("Sell: " + format(sell, ',.2f'))
            print ("Buy: " + format(buy, ',.2f'))
            print ("Contract Price: " + format(price, ',.2f'))
        
        profit = target - price - sell_exchange
        
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
        profit_buy = buy - price - sell_exchange
        profit_sell = sell - price - sell_exchange
        db_add_contract (contract_id, location_id, buy, sell, price, sell_exchange, items, items_exchange, \
                security, expiry, priority, region_id, profit_buy, profit_sell, volume, system_id)
        if priority > 0:
            print ("Contract ID: " + str(contract_id))
            print ("Sell: " + format(sell, ',.2f'))
            print ("Buy: " + format(buy, ',.2f'))
            print ("Contract Price: " + format(price, ',.2f'))
            profit = target - price
            print ("Awooga Profit " + format(profit, ',.2f'))

def main():
    global contracts
    global db_sde #SDE connection
    global db_contract
    global verbose
    global rig_groupids
    global dont_count_rigs
    global char # Class that holds all the security gubbins for ESI
    global forbidden_structures
    global broken_contracts

    print ("Startin' muta watch")
    print ("Searching regions:")
    print ("10000052 Kador")
    print ("10000069 Black Rise")
    print ("10000068 Verge Vendor")
    print ("10000016 Lonetrek")
    print ("10000067 Genesis")
    print ("10000065 Kor-Azor")
    print ("10000020 Tash-Murkon")
    print ("10000001 Derelick")
    print ("10000036 Devoid")
    print ("10000030 Heimatar")
    print ("10000042 Metropolis")
    print ("10000002 The Forge")
    print ("10000037 Everyshore")
    print ("10000032 Sinq Laison")
    print ("10000033 The Citadel")
    print ("10000043 Domain")
    print ("10000064 Essence")
    
    forbidden_structures = []
    broken_contracts = []

    regions = (10000052, 10000069, 10000068, 10000016, 10000067, 10000065, 10000020, 10000001, 10000036, 10000030, 10000042, 10000002, 10000037, 10000032, 10000033, 10000043, 10000064)
    verbose = False
    dont_count_rigs = True
    db_sde = sql_sde_connect_to_db ()
    db_contract = db_open_contract_db ()
    
    logging.basicConfig(filename='logMutas.log',level=logging.WARNING)
    char = esiChar("tokens.txt") #Currently only used to get structure solarsystem
    
    rig_groupids = get_rig_groupids ()
    while esi_get_status () != True:
        print ("ESI unavailable")
        sleep (30)

    while (1):
        for region_id in regions:
            check_region (region_id)
    print ("Exiting....")

    
if __name__ == "__main__":
    main()

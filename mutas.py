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
#Includes 'you will pay' items as well

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
    print ("Fetching appraisal")
    if len(text) == 0:
        print ("Error:  appraisal text empty")
        return 

    market = "jita"
    url = "https://evepraisal.com/appraisal.json?market=" + market + "&raw_textarea=" + text + "&persist=no"
    r = requests.post (url, headers=headers)
    
    if r.status_code !=200:
        print ("Error fetching appraisal: " + str(r.status_code))
        print (url)
        input ()
        #exit (1)

    appraisal = json.loads(r.text)
    return appraisal

def create_appraisal (contract_items):
    print ("Creating appraisal list")
    appraisal_text = ""
    for contract_item in contract_items:
        if 'is_blueprint_copy' in contract_item:
            continue
        # Seller is asking for item in return
        if contract_item['is_included'] is False:
            continue
        print (get_name_from_type_id(conn, contract_item['type_id']) + " x " + str(contract_item['quantity']))
        appraisal_text += get_name_from_type_id (conn, contract_item['type_id'])
        appraisal_text += " " + str(contract_item['quantity'])
        appraisal_text += "\r\n"
    return appraisal_text

def get_appraisal (contract_items):
    appraisal_text = create_appraisal (contract_items)
    appraisal = fetch_appraisal (appraisal_text)
    return appraisal

def get_contract_items (contract_id):
    print ("Getting items for contract_id: " + str(contract_id))
    items = []
    url = "https://esi.evetech.net/latest/contracts/public/items/" + str(contract_id) + "/?datasource=tranquility&page=1"
    r = requests.get (url, headers=headers)
    if r.status_code != 200:
        print ("get_contract_items: Error " + str(r.status_code))
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
    print ("Extracting contract_ids for type: " + str(contract_type))
    contract_ids = []
    prices = []
    for contract in contracts:
        if contract['type'] == contract_type and not check_if_expired (contract['date_expired']):
            contract_ids.append (contract['contract_id'])
            prices.append (contract['price'])

    return contract_ids, prices

def get_contract (contract_id):
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


def main():
    global contracts
    global conn
    print ("Startin' muta watch")
    region_id = input ("Enter in region id: ")
    #region_id = 10000016
    conn = sql_sde_connect_to_db ()
    do_security ()
    contracts = get_contracts_for_region (region_id)
    contract_ids = extract_contract_ids ("item_exchange", contracts)
    
    #Unpack the tuple - FIXME
    prices = contract_ids[1]
    contract_ids = contract_ids[0]
    
    for contract_id in contract_ids:
        print ("Contract ID: " + str(contract_id))
        contract_items = get_contract_items (contract_id)
        price = prices[contract_ids.index(contract_id)]
        print ("Contract Price: " + str(price))
        appraisal = get_appraisal (contract_items)
        try:
            print (appraisal['appraisal']['totals'])
            buy = appraisal['appraisal']['totals']['buy']
            sell = appraisal['appraisal']['totals']['sell']

            target = sell

            if target > price:
                profit = target - price
                print ("AWOOOGA PROFIT " + format(profit, ',f'))
                open_ui_for_contract (contract_id)
                input ()
        except NameError:
            print ("Error getting appraisal information for contract")
        except TypeError:
            print ("TypeError getting appraisal information")


    print ("Exiting....")

    
if __name__ == "__main__":
    main()

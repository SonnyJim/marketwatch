#!/usr/bin/env python3

from esipy import App
from esipy import EsiClient
from esipy import EsiSecurity
from esipy import EsiApp
from esipy.cache import FileCache
import pickle
import requests
import json
import xml.etree.ElementTree as ET

from time import sleep
from config import *
from sql_sde import *


global market_prices

cache = FileCache(path="/tmp")

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

def get_corp_blueprints ():
    op = app.op['corporations_corporation_id_blueprints'](corporation_id=corporation_id)
    r = client.request(op)
    if r.status != 200:
        print ("Error fetching corporation blueprints: " + str(r.status) + " " + str(r.error))
        return

    for i in r.data:
        print (i['type_id'])

def get_market_prices ():
    print ("Fetching latest market prices from ESI, like the adjusted ones because eeeeh")
    url = 'https://esi.evetech.net/latest/markets/prices/?datasource=tranquility'
    r = requests.get (url)
    market_prices = r.json()

    #TODO Dump these prices into an SQLite db and work with them from there.

def get_item_prices (materials):
    #print ("Fetching prices from EVEMarketer.com")
    url = 'https://api.evemarketer.com/ec/marketstat/json'
    r = requests.post(url, data= {'typeid':materials, 'usesystem':system_id})
    return r.json()

def get_system_cost_index (man_system_id, activity):
    #print ("Fetching system cost index for " + str(man_system_id))
    url = "http://api.eve-industry.org/system-cost-index.xml?id=" + str(man_system_id)
    r = requests.get (url)
    root = ET.fromstring (r.content)
    
    for element in root[0]:
        if element.tag == 'activity' and element.attrib['id'] == str(activity):
            system_cost_index = float(element.text)
            break

    return system_cost_index

def get_job_base_cost (bpid):
    #print ("Calculating job base cost")
    url = 'https://api.eve-industry.org/job-base-cost.xml?ids=' + str(bpid)
    r = requests.get (url)
    root = ET.fromstring (r.content)

    return float(root[0].text)

def get_manufacturing_price_for_item (conn, name, me, location):
    print ("Getting manufacturing price for item: " + str(name))
    bpid = get_bpid_for_name (conn, name)
    materials = get_materials_for_bp (conn, bpid)

    job_base_cost = get_job_base_cost (bpid)
    system_cost_index = get_system_cost_index (man_system_id, 1)
    structure_role_bonus = 1 - 0.03 # 3% bonus to job installation costs
    
    jobfee = job_base_cost * system_cost_index * structure_role_bonus
    pricelist = []

    for material in materials:
        pricelist.append (material[0])
    #Pricelist is a list of each itemid but no quantity   
    pricelist = get_item_prices (pricelist)

    total = 0
    materials_total = 0
    for i, material in enumerate(materials):
        me_material = round(material[1] * (1 - me)) #Calculate the quantity needed based on ME
        cost = float(pricelist[i]['sell']['min']) * me_material
        print (get_name_from_type_id(conn, material[0]) + " x " + str(me_material) + ": %.2f" % cost)
        materials_total = materials_total + cost

    total = total + materials_total + jobfee

    #print ("Materials total = {:,}".format(total))
    print ("Materials total: %.2f" %materials_total)
    print ("Job fee: %.2f" %jobfee)
    print ("Total: %.2f" %total)
    
    sell_price = get_item_prices (get_type_id_from_name(conn, name))
    sell_price = sell_price[0]['sell']['min']
    print ("Sell price: %.2f" %sell_price)
    print ("Profit: %.2f" %(sell_price - total))

def main():
    global conn
    #do_security()
    #get_corp_blueprints()
    #TODO Probably want to cache this
    #get_market_prices ()
    conn = sql_sde_connect_to_db ()
    print ("Enter in item name:")
    item = input()
    print ("Enter in ME:")
    me = int(input()) / 100
    get_manufacturing_price_for_item (conn, item, me, "")


    print ("Exiting....")

    
if __name__ == "__main__":
    main()

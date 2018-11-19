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
import sqlite3

from time import sleep
from esi_helper import esi_get_player_location
from esi_helper import esi_get_player_ship
from esi_helper import esi_get_player_online

from config import *

cache = FileCache(path="/tmp")

timeout = 5
sqlite_file = './location.sqlite'
conn = sqlite3.connect(sqlite_file)

class Char:
    def __init__(self, token_file):
        #Retrieve the tokens from the file
        with open(token_file, "rb") as fp:
            tokens_file = pickle.load(fp)
        fp.close()

        esi_app = EsiApp(cache=cache, cache_time=0, headers=headers)
        self.app = esi_app.get_latest_swagger

        self.security = EsiSecurity(
                redirect_uri=redirect_uri,
                client_id=client_id,
                secret_key=secret_key,
                headers=headers
                )

        self.client = EsiClient(
                retry_requests=True,
                headers=headers,
                security=self.security
                )

        self.security.update_token({
            'access_token': '',
            'expires_in': -1,
            'refresh_token': tokens_file['refresh_token']
            })

        tokens = self.security.refresh()
        api_info = self.security.verify()
        print ("security: Authenticated for " + str(api_info['Scopes']))

class PlayerData:
    station_id = 0
    solar_system_id = 0
    ship_type_id = 0
    ship_name = ""
    ship_item_id = 0

def create_database ():
    c = conn.cursor()
    c.execute ('''CREATE TABLE IF NOT EXISTS location (date TEXT PRIMARY KEY, station_id INTEGER, solar_system_id INTEGER, ship_type_id INTEGER, ship_item_id INTEGER, ship_name TEXT)''')
    conn.commit ()

def write_to_database (pd, time):
    print ("Something changed, updating database")
    c = conn.cursor ()
    params = (time, pd.station_id, pd.solar_system_id, pd.ship_type_id, pd.ship_item_id, pd.ship_name)
    print (params)
    c.execute ('INSERT INTO location VALUES (?,?,?,?,?,?)', params)
    conn.commit ()


def update_player_data (char):
    pd = PlayerData() 
    data = esi_get_player_location (char)
    #print (data)
    if 'station_id' in data:
        pd.station_id = data['station_id']
    else:
        pd.station_id = 0

    pd.solar_system_id = data['solar_system_id']

    data = esi_get_player_ship (char)
    pd.ship_type_id = data['ship_type_id']
    pd.ship_name = data['ship_name']
    pd.ship_item_id = data['ship_item_id']

    return pd

def player_tracker_loop (char):
    changed = False
    pd = PlayerData()
    pd_last = PlayerData()
    
    time = datetime.datetime.now()
    pd = update_player_data (char)
    pd_last = update_player_data (char)

    write_to_database (pd, time)

    while (True):
        if esi_get_player_online == False:
            print ("Player not online")
            sleep (timeout)
            return
            
        pd = update_player_data (char)
        time = datetime.datetime.now()
        
        if (pd.station_id != pd_last.station_id):
            pd_last.station_id = pd.station_id
            changed = True
            #print ("Changed station: " + str(pd.station_id))
        
        if (pd.solar_system_id != pd_last.solar_system_id):
            pd_last.solar_system_id = pd.solar_system_id
            changed = True
            #print ("Changed solar system: " + str(pd.solar_system_id))

        if (pd.ship_item_id != pd_last.ship_item_id):
            pd_last.ship_item_id = pd.ship_item_id
            pd_last.ship_type_id = pd.ship_type_id
            pd_last.ship_name = pd.ship_name
            changed = True
            #print ("Changed ship: " + str(pd.ship_name))

        if changed:
            write_to_database (pd, time)
            changed = False

        sleep (timeout)



def do_security():
    char = Char("tokens.txt")
    return char

def main():
    print ("Startin' Player tracker")
    create_database ()
    char = do_security()
    player_tracker_loop (char)
    print ("Exiting....")

    
if __name__ == "__main__":
    main()

#!/usr/bin/env python3

from esipy import App
from esipy import EsiClient
from esipy import EsiSecurity
from esipy import EsiApp
from esipy.cache import FileCache
import pickle
import requests
import json
import threading
import smtplib
from email.message import EmailMessage

from functools import lru_cache
from time import sleep
from config import *

cache = FileCache(path="/tmp")

class esiChar:
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

        self.character_id = api_info['CharacterID']
        self.name = api_info['CharacterName']
        #print (str(api_info))
        print ("security: " + self.name + " authenticated for " + str(api_info['Scopes']))

def esi_contract_is_still_valid (contract_id):
    url = "https://esi.evetech.net/latest/contracts/public/bids/"+ str(contract_id) + "/?datasource=tranquility&page=1"
    r = requests.get (url)
    #TODO This is stupid, we assume if it's still valid because we don't need auth to fetch the bids
    if r.status_code == 403:
        return False
    elif r.status_code == 404:
        return False
    else:
        return True

@lru_cache(maxsize=1024)
def esi_get_structure_information (structure_id, char):
    op = char.app.op['universe_structures_structure_id'](structure_id=structure_id)
    r = char.client.request(op)

    if r.status != 200:
        print ("distance: Couldn't get solar system for structure: error " + str(r.status))
        return None
    return r.data


@lru_cache(maxsize=1024)
def esi_get_station_information (station_id, char):
    op = char.app.op['universe_stations_station_id'](station_id=station_id)
    r = char.client.request(op)

    if r.status != 200:
        print ("distance: Couldn't get solar system for station: error " + str(r.status))
        return None
    return r.data

@lru_cache(maxsize=1024)
def esi_distance_from_station (origin, destination, flag, char):
    #print ("distance: Calculating route from " + str(origin) + " to " + str(destination))
    op = char.app.op['get_route_origin_destination'](origin=origin, destination=destination, flag=flag)
    r = char.client.request(op)

    if r.status != 200:
        print ("distance: Couldn't get distance from station: error " + str(r.status))
        return -1

    distance = len(r.data)
    return distance

def esi_get_status ():
    print ("Checking ESI status:")
    url = "https://esi.evetech.net/latest/status/?datasource=tranquility"
    r = requests.get (url)
    if r.status_code != 200:
        return False
    else:
        return True

@lru_cache(maxsize=1024)
def esi_get_info_for_typeid (type_id):
    url = "https://esi.evetech.net/latest/universe/types/"+ str(type_id)+"/?datasource=tranquility&language=en-us"
    r = requests.get (url)
    if r.status_code != 200:
        return
    data = json.loads(r.text)
    return data


@lru_cache(maxsize=1024)
def esi_get_name_from_id (type_id):
    url = "https://esi.evetech.net/latest/universe/names/?datasource=tranquility"
    post = "[ " + str(type_id) + " ]"
    r = requests.post (url, post)
    if r.status_code != 200:
        return "Unknown type_id " + str(type_id)

    data = json.loads(r.text)[0]
    return str(data['name'])

def esi_open_ui_for_type_id (type_id, char):
    print ("ui: Opening UI for item_id " + str(type_id))
    op = char.app.op['post_ui_openwindow_marketdetails'](type_id=type_id)
    ui = char.client.request(op)

    if (ui.status_code != 204):
        print ("ui: Error opening window: error "+ str(ui.status_code))

def esi_open_ui_for_contract (contract_id, char):
    print ("ui: Opening UI for contract_id " + str(contract_id))
    op = char.app.op['post_ui_openwindow_contract'](contract_id=contract_id)
    ui = char.client.request(op)


def esi_check_if_evemail_read (mail_id, char):
    #FIXME Need to get the character ID properly
    #print ("mail: Checking to see if mail_id " + str(mail_id) + " has been read")
    op = char.app.op['get_characters_character_id_mail_mail_id'](mail_id=mail_id, character_id=character_id)
    r = char.client.request(op)

    if (r.status != 200):
        print ("mail: Error fetching mail "+ str(ui.status_code))
        return False
   
    print (r.data)
    if 'read' in r.data:
        #print ("Mail read")
        return True
    else:
        return False

def esi_send_evemail (subject, body, character_id, char):
    #mail = {'approved_cost':10000, 'body':body, 'subject':subject, 'recipients':[{'recipient_id':corporation_id, 'recipient_type':'corporation'}]}
    mail = {'approved_cost':0, 'body':body, 'subject':subject, 'recipients':[{'recipient_id':character_id, 'recipient_type':'character'}]}
    op = char.app.op ['post_characters_character_id_mail'](
            character_id=mail_character_id,
            mail=mail)
    r = char.client.request(op)
    
    #Return the mailid
    return r.data

def esi_get_contracts_for_region (region_id):
    print ("Fetching public contracts for reqion: " + get_name_from_region_id (db_sde, region_id))
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



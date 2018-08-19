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

from time import sleep
from config import *

#FIXME Need to look at the range from the station for the buy orders

cache = FileCache(path="/tmp")

def distance_from_station (origin, destination):
    #print ("distance: Calculating route from " + str(origin) + " to " + str(destination))
    op = industry_char.app.op['get_route_origin_destination'](origin=origin, destination=destination)
    r = industry_char.client.request(op)

    if r.status != 200:
        print ("distance: Couldn't get distance from station: error " + str(r.status))
        return 1

    distance = len(r.data)
    return distance

def get_name_from_id (type_id):
    url = "https://esi.evetech.net/latest/universe/names/?datasource=tranquility"
    post = "[ " + str(type_id) + " ]"
    r = requests.post (url, post)
    if r.status_code != 200:
        return "Unknown type_id " + str(type_id)

    data = json.loads(r.text)[0]
    return str(data['name'])

def open_ui_for_type_id (type_id):
    print ("ui: Opening UI for item_id " + str(type_id))
    op = industry_char.app.op['post_ui_openwindow_marketdetails'](type_id=type_id)
    ui = industry_char.client.request(op)

    if (ui.status_code != 204):
        print ("ui: Error opening window: error "+ str(ui.status_code))

def check_if_evemail_read (mail_id):
    #print ("mail: Checking to see if mail_id " + str(mail_id) + " has been read")
    op = industry_char.app.op['get_characters_character_id_mail_mail_id'](mail_id=mail_id, character_id=character_id)
    r = industry_char.client.request(op)

    if (r.status != 200):
        print ("mail: Error fetching mail "+ str(ui.status_code))
        return False
   
    print (r.data)
    if 'read' in r.data:
        #print ("Mail read")
        return True
    else:
        return False

def send_evemail (subject, body):
    #mail = {'approved_cost':10000, 'body':body, 'subject':subject, 'recipients':[{'recipient_id':corporation_id, 'recipient_type':'corporation'}]}
    mail = {'approved_cost':0, 'body':body, 'subject':subject, 'recipients':[{'recipient_id':character_id, 'recipient_type':'character'}]}
    op = mail_char.app.op ['post_characters_character_id_mail'](
            character_id=mail_character_id,
            mail=mail)
    r = mail_char.client.request(op)
    
    #Return the mailid
    return r.data

def send_email (subject, body):
    msg = EmailMessage()
    msg['From'] = email_from
    msg['To'] = email_to
    msg['Subject'] = subject
    msg.set_content (body)
    server = smtplib.SMTP(email_smtp)
    server.send_message (msg)
    server.quit()

def send_notification (subject, body, type_id):
    print ("notify: Sending notification " + subject)
    mail_id = 0
    if notify_by_email:
        send_email (subject, body)
    if notify_by_evemail:
        mail_id = send_evemail (subject, body)
    if notify_by_ui:
        open_ui_for_type_id (type_id)

    return mail_id

def order_thread_exists (threads, order_id):
    for thread in threads:
        if int(thread.name) == int(order_id):
            return True
    return False

def get_corp_orders():
    name = get_name_from_id (corporation_id)
    print ("orders: Fetching market orders for " + name)
    threads = []
    
    while (1):
        op = industry_char.app.op['get_corporations_corporation_id_orders'](
                corporation_id=corporation_id
                    )
        orders = industry_char.client.request(op)
        if (orders.status != 200):
            print ("orders: Couldn't fetch any order data: error " + str(orders.status))
            exit (1)

        if len(orders.data) == 0:
                print ("orders: Couldn't find any order data")

        #Find the orders and start monitoring them if they aren't already
        for order in orders.data:
            if order['location_id'] == location_id and not order_thread_exists (threads, order['order_id']):
                    print ("orders: Found order_id " + str(order['order_id']))
                    
                    if 'is_buy_order' in order:
                        is_buy_order = True
                    else:
                        is_buy_order = False

                    #Start a new thread to monitor the price
                    t = threading.Thread(target=monitor_order, args=(order, is_buy_order), name=order['order_id'])
                    threads.append(t)
                    t.start()
        sleep(60)
        
#Monitors an order_id for changes
def monitor_order (order_mine, is_buy_order):

    name = get_name_from_id (order_mine['type_id'])
    if is_buy_order:
        buy_msg = "buy order"
    else:
        buy_msg = "sell order"

    print ("monitor: Starting monitor for " + buy_msg + " of " + name + "s (order_id " + str(order_mine['order_id']) + ")")
    
    #Start off assuming that we have the best price already
    best_price = order_mine['price']
    best_price_old = best_price

    volume_remain_old = order_mine['volume_remain']

    sent_notification = False
    mail_id = 0

    while (order_mine['volume_remain'] > 0):
        #Fetch all the orders for the type_id in the region
        op = industry_char.app.op['get_markets_region_id_orders'](region_id=region_id,type_id=order_mine['type_id'])
        orders = industry_char.client.request(op)
        
        if orders.status != 200:
            print ("monitor: Couldn't fetch orders: error " + str(orders.status))
            return 1
        
        order_mine_exists = False
        for order in orders.data:
            if is_buy_order and order['is_buy_order']: #Calculate the distance from the station for buy orders
                distance = distance_from_station (system_id, order['system_id'])
                if order['range'] == 'station' or order['range'] == 'solarsystem':
                    order_range = 1
                elif order['range'] == 'region':
                    order_range = 50
                else:
                    order_range = int(order['range'])
                if distance > order_range:
                    continue
            elif order['location_id'] != location_id: #ignore if it's a sell order that isn't this station
                continue
            #Found my own order, update it's details (price/quantity etc)
            if order['order_id'] == order_mine['order_id']:
                order_mine_exists = True
                order_mine = order

            #See what the best price is currently
            if is_buy_order and order['is_buy_order']:
                if order['price'] > best_price:
                    best_price = order['price']
            if is_buy_order == False and order['is_buy_order'] == False:
                if order['price'] < best_price:
                    best_price = order['price']

        #Check to see if we actually found our own order
        if len(order_mine) == 0 or order_mine_exists == False :
            subject = "EVE Marketwatch: sold out of " + name
            body = "I can't find order id " + str(order_mine['order_id']) + ", looks like we sold all " + str(order_mine['volume_total']) + " of the " + name + " we had listed"
            print ("monitor: " + body)
            mail_id = send_notification (subject, body, order_mine['type_id'])
            return 0

        #Notify us about the current state of our order
        #print ("monitor: " + name + " best price: " + str(best_price) + ", my price: " +str(order_mine['price']))
        
        if order_mine['volume_remain'] != volume_remain_old:
            volume_remain_old = order_mine['volume_remain']
            print ("monitor: " + name + " " + str(order_mine['volume_remain']) + "/" + str(order_mine['volume_total']))

        #Reset the sent_notification if we are currently the best price
        if best_price == order_mine['price']:
            if sent_notification:
                print ("monitor: Now currently best price for " + name)
            sent_notification = False
        
        #Check to see if we've read the evemail
        if mail_id != 0 and send_evemail == True:
            if check_if_evemail_read (mail_id):
                mail_id = 0
                sent_notification = False

        if is_buy_order and best_price > order_mine['price'] and sent_notification != True:
            subject = "EVE Marketwatch: " + name
            body = "monitor: Not winning " + name + " buy order, use price: " + str(best_price + 0.01)
            print (body)
            mail_id = send_notification (subject, body, order_mine['type_id'])
            sent_notification = True


        if is_buy_order == False and best_price < order_mine['price'] and sent_notification != True:
            subject = "EVE Marketwatch: " + name
            body = "monitor: Not winning " + name + " sell order, use price: " + str(best_price - 0.01)
            print (body)
            send_notification (subject, body, order_mine['type_id'])
            sent_notification = True

        sleep(30)
        
    print ("monitor: Finished monitoring item")


def do_security():
    global industry_char, mail_char

    industry_char = Char("tokens.txt")
    mail_char = Char("tokens_mail.txt")

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

def main():
    print ("Startin' Marketwatch")
    do_security()
    get_corp_orders()
    print ("Exiting....")

    
if __name__ == "__main__":
    main()

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

cache = FileCache(path="/tmp")
order_list = []

def get_name_from_id (type_id):
    url = "https://esi.evetech.net/latest/universe/names/?datasource=tranquility"
    post = "[ " + str(type_id) + " ]"
    r = requests.post (url, post)
    data = json.loads(r.text)[0]
    return str(data['name'])

#TODO
def order_list_remove (order_id):
    print ("Removing " + str(order_id) + " from orders_list")

def open_ui_for_type_id (type_id):
    print ("ui: Opening UI for item_id " + str(type_id))
    op = app.op['post_ui_openwindow_marketdetails'](type_id=type_id)
    ui = client.request(op)

    #if (ui.response != 204):
    #    print ("ui: something went wrong error "+ str(ui.code))
    #    return 1

#TODO
def send_evemail (subject, body):
    print ("Sending evemail")
    mail = {'approved_cost':10000, 'body':body, 'subject':subject, 'recipients':[{'recipient_id':corporation_id, 'recipient_type':'corporation'}]}
    op = app.op ['post_characters_character_id_mail'](
            character_id=character_id,
            mail=mail)
    r = client.request(op)
    print (r.data)

def send_email (subject, body):
    msg = EmailMessage()
    msg['From'] = email_from
    msg['To'] = email_to
    msg['Subject'] = subject
    msg.set_content (body)
    server = smtplib.SMTP('localhost')
    server.send_message (msg)
    server.quit()

def send_notification (subject, body, type_id):
    print ("notify: Sending notification " + subject)
    if notify_by_email:
        send_email (subject, body)
    if notify_by_evemail:
        send_evemail (subject, body)
    if notify_by_ui:
        open_ui_for_type_id (type_id)

def get_corp_orders():
    name = get_name_from_id (corporation_id)
    print ("orders: Fetching market orders for " + name)

    op = app.op['get_corporations_corporation_id_orders'](
            corporation_id=corporation_id
                )
    orders = client.request(op)
    if (orders.data == None):
        print ("orders: Couldn't find any orders")
        return 1
    
    threads = []

    #Find the orders and add them to the list if they aren't there already
    for order in orders.data:
        if order['location_id'] == location_id and order['order_id'] not in order_list:
                print ("orders: Found order_id " + str(order['order_id']))
                
                if 'is_buy_order' in order:
                    is_buy_order = True
                else:
                    is_buy_order = False

                order_list.append({'order_id':order['order_id'], 'type_id':order['type_id'], 'is_buy_order':is_buy_order})
                #Start a new thread to monitor the price
                t = threading.Thread(target=monitor_order, args=(order, is_buy_order), name=order['order_id'])
                threads.append(t)
                t.start()
    
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

    volume_remain_old = order_mine['volume_remain']

    sent_notification = False
    
    while (order_mine['volume_remain'] > 0):
        #Fetch all the orders for the region
        op = app.op['get_markets_region_id_orders'](region_id=region_id,type_id=order_mine['type_id'])
        orders = client.request(op)
        order_mine_exists = False

        if (orders.data == None):
            print ("monitor: Couldn't find any orders")
            return 1
        
        for order in orders.data:
            #Ignore any that aren't in the right location
            if order['location_id'] != location_id:
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
        if len(order_mine) == 0 or order_mine_exists == False:
            print ("monitor: Couldn't find my order_id: "+ str(order_mine['order_id']) + " " + name + ", maybe it's sold out")
            subject = "EVE Marketwatch: sold out of " + name
            body = "I can't find order id " + str(order_mine['order_id']) + ", looks like we sold all " + str(order_mine['volume_total']) + " of the " + name + " we had listed"
            send_notification (subject, body, order_mine['type_id'])
            return 1

        #Notify us about the current state of our order
        #print ("monitor: " + name + " best price: " + str(best_price) + ", my price: " +str(order_mine['price']))

        if order_mine['volume_remain'] < volume_remain_old:
            volume_remain_old = order_mine['volume_remain']
            print ("monitor: " + name + " " + str(order_mine['volume_remain']) + "/" + str(order_mine['volume_total']))

        #Reset the sent_notification if we are currently the best price
        if best_price == order_mine['price']:
            sent_notification = False
        
        if is_buy_order and best_price > order_mine['price'] and sent_notification != True:
            subject = "EVE Marketwatch: " + name
            body = "monitor: Not winning " + name + " buy order, use price: " + str(best_price + 0.01)
            print (body)
            send_notification (subject, body, order_mine['type_id'])
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
    global client
    global app
    print ("security: Authenticating")
    #Open up the token file
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


def main():
    print ("Startin' Marketwatch")
    do_security()
    get_corp_orders()

    
if __name__ == "__main__":
    main()

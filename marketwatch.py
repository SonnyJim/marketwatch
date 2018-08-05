#!/usr/bin/env python3

from esipy import App
from esipy import EsiClient
from esipy import EsiSecurity
from esipy import EsiApp
from esipy.cache import FileCache
import pickle
from time import sleep
from config import *

cache = FileCache(path="/tmp")
order_list = []

def order_list_remove (order_id):
    print ("Removing " + str(order_id) + " from orders_list")

def get_corp_orders():
    print ("Fetching market orders for corporation_id " + str(corporation_id))

    op = app.op['get_corporations_corporation_id_orders'](
            corporation_id=corporation_id
                )
    orders = client.request(op)
    if (orders.data == None):
        print ("Couldn't find any orders")
        return 1

    #Find the orders and add them to the list if they aren't there already
    for order in orders.data:
        if order['location_id'] == location_id and order['order_id'] not in order_list:
                print ("orders:  Found new order_id " + str(order['order_id']))
                
                if 'is_buy_order' in order:
                    is_buy_order = True
                else:
                    is_buy_order = False

                order_list.append({'order_id':order['order_id'], 'type_id':order['type_id'], 'is_buy_order':is_buy_order})
                monitor_order (order, is_buy_order)
    

def monitor_order (order_mine, is_buy_order):
    if is_buy_order:
        buy_msg = "buy order"
    else:
        buy_msg = "sell order"

    print ("monitor: Starting monitor for " + buy_msg + " type:" +str(order_mine['type_id']) +" order_id:" + str(order_mine['order_id']))
    
    best_price = order_mine['price']
    
    while (order_mine['volume_remain'] > 0):
        #Fetch all the orders for the region
        op = app.op['get_markets_region_id_orders'](region_id=region_id,type_id=order_mine['type_id'])
        orders = client.request(op)
        order_mine_exists = False

        if (orders.data == None):
            print ("Couldn't find any orders")
            return 1
        
        for order in orders.data:
            #Ignore any that aren't in the right location
            if order['location_id'] != location_id:
                continue
            if order['order_id'] == order_mine['order_id']:
                order_mine_exists = True
                order_mine = order
            if is_buy_order and order['is_buy_order']:
                if order['price'] > best_price:
                    best_price = order['price']
            if is_buy_order == False and order['is_buy_order'] == False:
                if order['price'] < best_price:
                    best_price = order['price']


        if len(order_mine) == 0 or order_mine_exists == False:
            print ("Couldn't find my order_id: "+ str(order_mine['order_id']) + ", maybe it's sold out")
            return 1
        
        print ("Best price: " + str(best_price) + " My price: " +str(order_mine['price']))
        if is_buy_order and best_price > order_mine['price']:
            print ("Not winning sell order, use price: " + str(best_price + 0.01))

        if is_buy_order == False and best_price < order_mine['price']:
            print ("Not winning sell order, use price: " + str(best_price - 0.01))

        sleep(30)
        
    print ("monitor: Finished monitoring item")


def do_security():
    global client
    global app
    print ("Authenticating")
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
    print ("Authenticated for " + str(api_info['Scopes']))


def main():
    print ("Startin' Marketwatch")
    do_security()
    get_corp_orders()

    
if __name__ == "__main__":
    main()

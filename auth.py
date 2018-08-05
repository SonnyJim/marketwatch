#!/usr/bin/env python3

from esipy import App
from esipy import EsiClient
from esipy import EsiSecurity
from esipy import EsiApp
from esipy.cache import FileCache
import pickle
from config import *


cache = FileCache(path="/tmp")

scopes=['esi-mail.send_mail.v1', 'esi-markets.read_corporation_orders.v1', 'esi-ui.open_window.v1']
    
def main():
    print ("Startin' Auth")
    esi_app = EsiApp(cache=cache, cache_time=0)
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

    print ("Open link in browser and authorize")
    print (security.get_auth_uri(scopes=scopes))
    code = input ("Enter in code:\n")
    tokens = security.auth(code)
    print (tokens)
    print ("\n Writing tokens to tokens.txt")
    with open('tokens.txt', 'wb') as fp:
        pickle.dump(tokens, fp)
    fp.close()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3

from esipy import App
from esipy import EsiClient
from esipy import EsiSecurity
from esipy import EsiApp
from esipy.cache import FileCache
import pickle
from config import *

cache = FileCache(path="/tmp")

mail_scopes=['esi-mail.send_mail.v1']
    
industry_scopes=['esi-markets.read_corporation_orders.v1', 'esi-mail.read_mail.v1', 
        'esi-ui.open_window.v1', 'esi-industry.read_corporation_jobs.v1',
        'esi-corporations.read_blueprints.v1']

def do_security (tokens_file, scopes):
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
    print ("\n Writing tokens to " + str(tokens_file))
    with open(tokens_file, 'wb') as fp:
        pickle.dump(tokens, fp)
    fp.close()


def main():
    print ("Startin' Auth")
    print ("Authenticating for industry char")
    do_security ('tokens.txt', industry_scopes)
    print ("Authenticating for mail char")
    do_security ('tokens_mail.txt', mail_scopes)
    print ("Finished")

if __name__ == "__main__":
    main()

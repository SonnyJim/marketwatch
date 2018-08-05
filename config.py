#character_id, location_id, region_id and corporation_id should be integers (ie: unquoted)
character_id = 
location_id = 
region_id = 
corporation_id = 

#Use the same settings you used in https://developers.eveonline.com/applications
redirect_uri=""
client_id=""
secret_key=""

#Use a descriptive header otherwise CCP go bleh
headers={"User-Agent": "A descriptive user agent"}

#Notification settings
notify_by_email=True
notify_by_evemail=False
notify_by_ui=False #Open up the market details for the item in the EVE Client
email_to=""
email_from=""
#Address of your smtp server
email_smtp=""

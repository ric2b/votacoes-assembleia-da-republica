import os
from dotenv import load_dotenv
from mastodon import Mastodon

load_dotenv()
MASTODON_ACCESS_TOKEN = os.environ['MASTODON_ACCESS_TOKEN']

m = Mastodon(access_token=MASTODON_ACCESS_TOKEN, api_base_url="https://masto.pt")

statuses_count = m.me()['statuses_count']

input(f'Delete {statuses_count} statuses? ^C to cancel')

for status in m.timeline():
    id = status['id']
    print(f'deleting {id}')
    m.status_delete(id)

import os
import sys
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from mastodon import Mastodon
from time import sleep

since_minutes_ago = int(sys.argv[1] if len(sys.argv) > 1 else 1)

load_dotenv()
MASTODON_ACCESS_TOKEN = os.environ['MASTODON_ACCESS_TOKEN']

m = Mastodon(access_token=MASTODON_ACCESS_TOKEN, api_base_url="https://masto.pt")
my_id = m.me().id


while True:
    # input(f'Delete {len(statuses_to_delete)} statuses? ^C to cancel')
    statuses_to_delete = [s for s in m.account_statuses(id=my_id, limit=30) if s['created_at'] >= datetime.now(timezone.utc) - timedelta(minutes=since_minutes_ago)]
    if not statuses_to_delete:
        break

    print(f'Deleting {len(statuses_to_delete)} statuses since {since_minutes_ago} minutes ago')
    for status in statuses_to_delete:
        id = status['id']
        print(f'deleting {id}')
        m.status_delete(id)

    if len(statuses_to_delete) >= 30:
        print('waiting for the rate limit to expire')
        sleep(30*60) # rate limits are 30 deletes per 30 minutes


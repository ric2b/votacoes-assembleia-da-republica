import os
import sys
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from mastodon import Mastodon

since_minutes_ago = int(sys.argv[1] if len(sys.argv) > 1 else 1)

load_dotenv()
MASTODON_ACCESS_TOKEN = os.environ['MASTODON_ACCESS_TOKEN']

m = Mastodon(access_token=MASTODON_ACCESS_TOKEN, api_base_url="https://masto.pt")

statuses_to_delete = [s for s in m.timeline() if s['created_at'] >= datetime.now(timezone.utc) - timedelta(minutes=since_minutes_ago)]

# input(f'Delete {len(statuses_to_delete)} statuses? ^C to cancel')
print(f'Deleting {len(statuses_to_delete)} statuses since {since_minutes_ago} minutes ago')

for status in statuses_to_delete:
    id = status['id']
    print(f'deleting {id}')
    m.status_delete(id)

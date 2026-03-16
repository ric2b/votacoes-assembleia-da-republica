import os
import sys
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from mastodon import Mastodon

since_minutes_ago = int(sys.argv[1] if len(sys.argv) > 1 else 1)

load_dotenv()
MASTODON_ACCESS_TOKEN = os.environ["MASTODON_ACCESS_TOKEN"]

m = Mastodon(access_token=MASTODON_ACCESS_TOKEN, api_base_url="https://masto.pt")
my_id = m.me().id
since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes_ago)

count = 0
page = m.account_statuses(id=my_id, limit=40)
while page:
    matching = [s for s in page if s["created_at"] >= since]
    count += len(matching)
    if len(matching) < len(page):
        break
    page = m.fetch_next(page)

print(f"{count} statuses in the last {since_minutes_ago} minutes")

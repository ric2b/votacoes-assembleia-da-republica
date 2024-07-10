import os
from mastodon import Mastodon

MASTODON_ACCESS_TOKEN = os.environ['MASTODON_ACCESS_TOKEN']
DEBUG_MODE = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'

class MastodonClient:
    def __init__(self) -> None:
        self.client = Mastodon(access_token=MASTODON_ACCESS_TOKEN, api_base_url="https://masto.pt")

    def post_vote(self, rendered_vote: str, idempotency_key = None) -> str:
        if DEBUG_MODE:
            print(f'would post vote:')
            print(rendered_vote)
            print('--------------------')
            return

        self.client.status_post(rendered_vote, idempotency_key = idempotency_key)

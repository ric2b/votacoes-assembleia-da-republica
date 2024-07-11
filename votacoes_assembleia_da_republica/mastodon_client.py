import os
from mastodon import Mastodon

class MastodonClient:
    def __init__(self) -> None:
        self.client = Mastodon(access_token=self.access_token, api_base_url=self.api_base_url)

    def post_vote(self, rendered_vote: str, idempotency_key = None) -> str:
        if self.debug_mode:
            print(f'would post vote:')
            print(rendered_vote)
            print('--------------------')
            return

        self.client.status_post(rendered_vote, idempotency_key = idempotency_key)

    @property
    def api_base_url(self):
        return os.getenv('MASTODON_API_BASE_URL', 'https://masto.pt')

    @property
    def access_token(self):
        return os.getenv('MASTODON_ACCESS_TOKEN')

    @property
    def debug_mode(self):
        return os.getenv('DEBUG_MODE', 'false').lower() == 'true'

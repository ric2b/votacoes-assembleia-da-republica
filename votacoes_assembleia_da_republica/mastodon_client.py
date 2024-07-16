import os
from mastodon import Mastodon

class MastodonClient:
    def __init__(self) -> None:
        if not self.debug_mode:
            self.client = Mastodon(access_token=self.access_token, api_base_url=self.api_base_url)

    def start_vote_thread(self, rendered_thread: str, idempotency_key = None) -> dict:
        if self.debug_mode:
            print(f'would post thread:')
            print(rendered_thread)
            print('--------------------')
            return

        return self.client.status_post(rendered_thread, idempotency_key = idempotency_key, language = 'pt')

    def post_vote(self, rendered_vote: str, reply_to: dict, idempotency_key = None) -> dict:
        if self.debug_mode:
            print(f'would post vote:')
            print(rendered_vote)
            print('--------------------')
            return

        return self.client.status_reply(reply_to, rendered_vote, visibility = 'unlisted', idempotency_key = idempotency_key, language = 'pt')

    @property
    def api_base_url(self):
        return os.getenv('MASTODON_API_BASE_URL', 'https://masto.pt')

    @property
    def access_token(self):
        return os.getenv('MASTODON_ACCESS_TOKEN')

    @property
    def debug_mode(self):
        return os.getenv('DEBUG_MODE', 'false').lower() == 'true'

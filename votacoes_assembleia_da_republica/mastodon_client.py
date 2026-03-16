import os
from mastodon import Mastodon


class MastodonClient:
    def __init__(self) -> None:
        if not self.debug_mode:
            self.client = Mastodon(access_token=self.access_token, api_base_url=self.api_base_url)

    def start_vote_thread(self, rendered_thread: str, idempotency_key=None) -> dict:
        if self.debug_mode:
            print("would post thread:")
            print(rendered_thread)
            print("--------------------")
            return

        return self.client.status_post(rendered_thread, idempotency_key=idempotency_key, language="pt")

    def latest_post_id(self) -> str | None:
        if self.debug_mode:
            return None
        me = self.client.me()
        statuses = self.client.account_statuses(me["id"], limit=1)
        if not statuses:
            return None
        return str(statuses[0]["id"])

    def post_vote(self, rendered_vote: str, reply_to: dict, idempotency_key=None) -> dict:
        if self.debug_mode:
            print("would post vote:")
            print(rendered_vote)
            print("--------------------")
            return

        return self.client.status_post(rendered_vote, in_reply_to_id=reply_to.id, visibility="unlisted", idempotency_key=idempotency_key, language="pt")

    @property
    def api_base_url(self):
        return os.getenv("MASTODON_API_BASE_URL", "https://masto.pt")

    @property
    def access_token(self):
        return os.getenv("MASTODON_ACCESS_TOKEN")

    @property
    def debug_mode(self):
        return os.getenv("DEBUG_MODE", "false").lower() == "true"

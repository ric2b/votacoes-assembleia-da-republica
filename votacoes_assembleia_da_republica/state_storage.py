import json
import os
import requests
import sys

class StateStorage:
    def __init__(self, legislature, file_path = 'state.json'):
        self.legislature = legislature
        self.file_path = file_path

    def __enter__(self):
        try:
            with open(self.file_path, 'r') as state_file:
                self.state = json.load(state_file)
        except FileNotFoundError:
            self.state = {}

        return self

    def __exit__(self, *args):
        if not self.debug_mode:
            with open(self.file_path, 'w') as state_file:
                json.dump(self.state, state_file)
            self.update_repo_variable(self.state)

    def mark_vote_published(self, vote_id: str) -> None:
        self.state[vote_id] = 'published'

    def mark_vote_errored(self, vote_id: str) -> None:
        self.state[vote_id] = 'errored'

    def skip_vote(self, vote_id: str) -> None:
        if vote_id not in self.state:
            self.state[vote_id] = 'skipped'

    def is_new_vote(self, vote_id: str) -> bool:
        return vote_id not in self.state

    def get_vote_state(self, vote_id: str) -> str:
        return self.state[vote_id]

    def update_repo_variable(self, state: dict) -> None:
        url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/actions/variables/STATE_{self.legislature}"
        headers = { "Accept": "application/vnd.github.v3+json", "Authorization": f"token {self.gh_token}" }

        try:
            response = requests.patch(url, headers=headers, json={ "value": state })

            if response.status_code not in (201, 204):
                print(f"Error updating variable: {response.status_code} - {response.text}", file=sys.stderr)
                response.raise_for_status()
        except Exception as e:
            print(f"Error saving data: {e}", file=sys.stderr)
            raise e

    @property
    def gh_variable_url(self):
        return f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/actions/variables/STATE_{self.legislature}"

    @property
    def gh_token(self):
        return os.environ.get('GH_VARIABLE_UPDATE_TOKEN')

    @property
    def repo_owner(self):
        return os.environ.get('REPO_OWNER')

    @property
    def repo_name(self):
        return os.environ.get('REPO_PATH').split("/")[-1]

    @property
    def debug_mode(self):
        return os.getenv('DEBUG_MODE', 'false').lower() == 'true'

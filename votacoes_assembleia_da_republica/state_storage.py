import base64
import gzip
import json
import os
import requests


def _compress_state(state: dict) -> str:
    return base64.b64encode(gzip.compress(json.dumps(state).encode())).decode()


def _decompress_state(value: str) -> dict:
    try:
        return json.loads(gzip.decompress(base64.b64decode(value, validate=True)))
    except Exception:
        return json.loads(value)


class StateStorage:
    def __init__(self, legislature, file_path="state.json", use_github=False):
        self.legislature = legislature
        self.file_path = file_path
        self.use_github = use_github

    def __enter__(self):
        if self.use_github:
            self.state = self.read_repo_variable(self.legislature)
        else:
            try:
                with open(self.file_path, "r") as state_file:
                    self.state = json.load(state_file)
            except FileNotFoundError:
                self.state = {}

        return self

    def __exit__(self, *args):
        with open(self.file_path, "w") as state_file:
            json.dump(self.state, state_file)

        if self.use_github:
            self.update_repo_variable(self.state)

    def mark_vote_published(self, vote_id: str) -> None:
        self.state[vote_id] = "published"

    def mark_vote_errored(self, vote_id: str) -> None:
        self.state[vote_id] = "errored"

    def skip_vote(self, vote_id: str) -> None:
        if vote_id not in self.state:
            self.state[vote_id] = "skipped"

    def is_new_vote(self, vote_id: str) -> bool:
        return vote_id not in self.state

    def get_vote_state(self, vote_id: str) -> str:
        return self.state[vote_id]

    def variable_url(self, legislature: str) -> str:
        return f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/actions/variables/STATE_{legislature}"

    def read_repo_variable(self, legislature: str) -> dict:
        url = self.variable_url(legislature)
        headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.gh_token}"}
        response = requests.get(url, headers=headers).json()

        print(f"Read variable {response['name']} updated at: {response['updated_at']}")
        return _decompress_state(response["value"])

    def update_repo_variable(self, state: dict) -> None:
        url = self.variable_url(self.legislature)
        headers = {"Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.gh_token}"}

        try:
            response = requests.patch(url, headers=headers, json={"value": _compress_state(state)})

            if response.status_code not in (201, 204):
                print(f"Error updating variable: {response.status_code} - {response.text}")
                response.raise_for_status()
        except Exception as e:
            print(f"Error saving data: {e}")
            raise e

    @property
    def gh_variable_url(self):
        return f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/actions/variables/STATE_{self.legislature}"

    @property
    def gh_token(self):
        return os.environ.get("GH_VARIABLE_UPDATE_TOKEN")

    @property
    def repo_owner(self):
        return os.environ.get("REPO_OWNER")

    @property
    def repo_name(self):
        return os.environ.get("REPO_PATH").split("/")[-1]

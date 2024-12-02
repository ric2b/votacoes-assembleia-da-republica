import json

class StateStorage:
    def __init__(self, file_path = 'state.json'):
        self.file_path = file_path

    def __enter__(self):
        try:
            with open(self.file_path, 'r') as state_file:
                self.state = json.load(state_file)
        except FileNotFoundError:
            self.state = {}

        return self

    def __exit__(self, *args):
        with open(self.file_path, 'w') as state_file:
            json.dump(self.state, state_file)

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

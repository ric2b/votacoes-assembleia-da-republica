import json
from votacoes_assembleia_da_republica.state_storage import _decompress_state

with open("state.json.gzip.b64", "r") as f:
    state = _decompress_state(f.read())

with open("state.json", "w") as f:
    json.dump(state, f)

print("Written to state.json")

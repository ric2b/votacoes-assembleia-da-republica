import json
from votacoes_assembleia_da_republica.state_storage import _compress_state

compressed = _compress_state(json.load(open("state.json")))

with open("state.json.gzip.b64", "w") as f:
    f.write(compressed)

print("Written to state.json.gzip.b64")

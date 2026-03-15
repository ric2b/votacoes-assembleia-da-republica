import json

from votacoes_assembleia_da_republica.state_storage import _compress_state, _decompress_state


def test_compress_and_decompress_roundtrip():
    state = {"126496": "published", "126516": "errored", "999": "skipped"}
    assert _decompress_state(_compress_state(state)) == state


def test_compressed_state_is_smaller_than_plain_json():
    state = {str(i): "published" for i in range(2000)}
    assert len(_compress_state(state)) < len(json.dumps(state))


def test_decompress_falls_back_to_plain_json():
    state = {"126496": "published"}
    assert _decompress_state(json.dumps(state)) == state

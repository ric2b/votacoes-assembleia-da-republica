import json
import os
import pytest
import requests_mock
from textwrap import dedent
from urllib.parse import unquote_plus

from votacoes_assembleia_da_republica.update_account import update
from votacoes_assembleia_da_republica.fetch_votes import JSON_URIS

@pytest.fixture(autouse=True)
def disable_debug_mode(monkeypatch):
    monkeypatch.setenv('DEBUG_MODE', 'false')

def test_update_doesnt_crash_if_there_are_no_votes(requests_mock, tmp_path):
    with open('tests/files/legislatures/empty_example.json', 'r') as legislature:
        requests_mock.get(JSON_URIS['XVI'], text=legislature.read())

    update('XVI', tmp_path / 'state.json')

    assert requests_mock.called
    assert requests_mock.call_count == 1

def test_update_doesnt_crash_if_there_are_a_few_votes(requests_mock, tmp_path):
    with open('tests/files/legislatures/minimal_example.json', 'r') as legislature:
        requests_mock.get(JSON_URIS['XVI'], text=legislature.read())

    requests_mock.get('https://masto.pt/api/v1/instance', status_code = 200)
    requests_mock.post('https://masto.pt/api/v1/statuses', json = {})
    update('XVI', tmp_path / 'state.json')

    assert requests_mock.called
    assert [request.hostname for request in requests_mock.request_history] == ['app.parlamento.pt', 'masto.pt', 'masto.pt']
    assert requests_mock.call_count == 3

    assert unquote_plus(requests_mock.last_request.body) == dedent(
        """\
        status=📝️️ Constituição de uma comissão de inquérito parlamentar ao processo de alteração da propriedade do Global Media Group envolvendo o World Opportunity Fund, Lda.
        🔗 Inquérito Parlamentar (PAN) - http://app.parlamento.pt/webutils/docs/doc.pdf?path=6148523063484d364c793968636d356c6443397a6158526c63793959566b6c4d5a5763765247396a6457316c626e527663306c7561574e7059585270646d45765a4446694d546c684e3251745954686c5a6930305a4745784c54686a5a4755744e6d526a4d544d314f544268596a646a4c6d52765933673d&fich=d1b19a7d-a8ef-4da1-8cde-6dc13590ab7c.docx&Inline=true

        🔴 Rejeitado

        🗳️ Votação Deliberação (2024-04-19):
        👍 IL, BE, PCP, L, PAN
        🤷 CH
        👎 PSD, PS, CDS-PP
        """
    )

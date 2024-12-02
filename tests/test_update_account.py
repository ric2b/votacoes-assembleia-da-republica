import json
import os
import pytest
import requests_mock
from textwrap import dedent
from urllib.parse import unquote_plus

from votacoes_assembleia_da_republica.update_account import update, render_vote, StateStorage
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

def test_render_vote_cuts_down_text_down_to_the_500_char_limit():
    test_vote = {
            'vote_id': '12345',
            'result': 'Rejeitado',
            'vote_detail': 'unanime',
            'date': '2024-04-10',
            'authors': ['author 1', 'author 2'],
            'initiative_type': 'Projeto de Lei',
            'title': 1000 * 'A',
            'phase': 'Entrada',
            'initiative_uri': 'http://app.parlamento.pt/webutils/docs/doc.pdf?path=6148523063484d364c793968636d356c6443397a6158526c63793959566b6c4d5a5763765247396a6457316c626e527663306c7561574e7059585270646d4576597a466b5a6d453459544d744d475a685a5330304d32557a4c5749325a6d4d744e6a6b78596a55794d5449304f47517a4c6d52765933673d&fich=c1dfa8a3-0fae-43e3-b6fc-691b521248d3.docx&Inline=true',
    }

    assert len(render_vote(test_vote)) - len(test_vote['initiative_uri']) + 23 == 500

def test_update_still_tries_to_save_state_if_a_post_errors_out(requests_mock, tmp_path):
    with open('tests/files/legislatures/minimal_example_approved_and_rejected.json', 'r') as legislature:
        requests_mock.get(JSON_URIS['XVI'], text=legislature.read())

    account = { 'id': 1, 'acct': 'user@server.com' }

    requests_mock.get('https://masto.pt/api/v1/instance', status_code = 200)
    requests_mock.get('https://masto.pt/api/v1/accounts/verify_credentials', status_code = 200, json = account)
    requests_mock.post('https://masto.pt/api/v1/statuses', [
        {'json': { 'id': 1, 'account': account, 'mentions': []}},
        {'status_code': 422, 'text': 'Validation failed: Text limite de caracter excedeu 500'},
        {'json': { 'id': 2, 'account': account, 'mentions': []}},
        {'json': { 'id': 126516, 'account': account, 'mentions': []}},
    ])

    state_file_path = tmp_path / 'state.json'
    update('XVI', state_file_path)

    assert requests_mock.called
    assert all(request.hostname in ['app.parlamento.pt', 'masto.pt'] for request in requests_mock.request_history)
    assert requests_mock.call_count == 7

    with StateStorage(file_path = state_file_path) as state:
        assert state.get_vote_state('126496') == 'published'
        assert state.get_vote_state('126516') == 'errored'

def test_update_makes_no_mastodon_requests_when_debug_mode_is_enabled(requests_mock, tmp_path, monkeypatch):
    monkeypatch.setenv('DEBUG_MODE', 'true')

    with open('tests/files/legislatures/minimal_example_approved_and_rejected.json', 'r') as legislature:
        requests_mock.get(JSON_URIS['XVI'], text=legislature.read())

    update('XVI', tmp_path / 'state.json')

    assert requests_mock.called
    assert all(request.hostname == 'app.parlamento.pt' for request in requests_mock.request_history)
    assert requests_mock.call_count == 1

def test_update_creates_one_thread_if_there_are_only_votes_with_one_result(requests_mock, tmp_path):
    with open('tests/files/legislatures/minimal_example.json', 'r') as legislature:
        requests_mock.get(JSON_URIS['XVI'], text=legislature.read())

    user_name = 'user@server.com'
    account = { 'id': 1, 'acct': user_name }
    thread_id = 1

    requests_mock.get('https://masto.pt/api/v1/instance', status_code = 200)
    requests_mock.get('https://masto.pt/api/v1/accounts/verify_credentials', status_code = 200, json = account)
    requests_mock.post('https://masto.pt/api/v1/statuses', json = { 'id': thread_id, 'account': account, 'mentions': []})

    update('XVI', tmp_path / 'state.json')

    assert requests_mock.called
    assert all(request.hostname in ['app.parlamento.pt', 'masto.pt'] for request in requests_mock.request_history)
    assert requests_mock.call_count == 5

    status_requests = [request for request in requests_mock.request_history if request.url == 'https://masto.pt/api/v1/statuses']

    assert unquote_plus(status_requests[0].body) == dedent(
        f"""\
        status=🔴 Rejeitadas - Votações na Assembleia da República (entre 2024-04-19 e 2024-04-19)

        Veja as votações individuais nas respostas 🧵
        &language=pt"""
    )
    assert unquote_plus(status_requests[1].body) == dedent(
        f"""\
        status=@{user_name} 📝️️ Constituição de uma comissão de inquérito parlamentar ao processo de alteração da propriedade do Global Media Group envolvendo o World Opportunity Fund, Lda.
        🔗 Inquérito Parlamentar (PAN) - http://app.parlamento.pt/webutils/docs/doc.pdf?path=6148523063484d364c793968636d356c6443397a6158526c63793959566b6c4d5a5763765247396a6457316c626e527663306c7561574e7059585270646d45765a4446694d546c684e3251745954686c5a6930305a4745784c54686a5a4755744e6d526a4d544d314f544268596a646a4c6d52765933673d&fich=d1b19a7d-a8ef-4da1-8cde-6dc13590ab7c.docx&Inline=true

        🔴 Rejeitado

        🗳️ Votação Deliberação (2024-04-19):
        👍 IL, BE, PCP, L, PAN
        🤷 CH
        👎 PSD, PS, CDS-PP
        &in_reply_to_id={thread_id}&visibility=unlisted&language=pt"""
    )

def test_update_creates_two_threads_if_there_both_approved_and_rejected_votes(requests_mock, tmp_path):
    with open('tests/files/legislatures/minimal_example_approved_and_rejected.json', 'r') as legislature:
        requests_mock.get(JSON_URIS['XVI'], text=legislature.read())

    user_name = 'user@server.com'
    account = { 'id': 1, 'acct': user_name }
    approved_thread_id = 1
    rejected_thread_id = 2

    requests_mock.get('https://masto.pt/api/v1/instance', status_code = 200)
    requests_mock.get('https://masto.pt/api/v1/accounts/verify_credentials', status_code = 200, json = account)
    requests_mock.post('https://masto.pt/api/v1/statuses', [
        { 'json': { 'id': approved_thread_id, 'account': account, 'mentions': [] } },
        { 'json': { 'id': rejected_thread_id, 'account': account, 'mentions': [] } },
    ])

    update('XVI', tmp_path / 'state.json')

    assert requests_mock.called
    assert all(request.hostname in ['app.parlamento.pt', 'masto.pt'] for request in requests_mock.request_history)
    assert requests_mock.call_count == 7

    status_requests = [request for request in requests_mock.request_history if request.url == 'https://masto.pt/api/v1/statuses']

    assert unquote_plus(status_requests[0].body) == dedent(
        f"""\
        status=🟢 Aprovadas - Votações na Assembleia da República (entre 2024-04-24 e 2024-04-24)

        Veja as votações individuais nas respostas 🧵
        &language=pt"""
    )
    assert unquote_plus(status_requests[1].body) == dedent(
        f"""\
        status=@{user_name} 📝️️ Altera o Código do Imposto sobre o Rendimento das Pessoas Singulares
        🔗 Projeto de Lei (PS) - http://app.parlamento.pt/webutils/docs/doc.pdf?path=6148523063484d364c793968636d356c6443397a6158526c63793959566b6c4d5a5763765247396a6457316c626e527663306c7561574e7059585270646d45764d545a6a4f575a6b5a6a6b744e4751334e4330304d6d49344c574a6b5a6a49744d6d566b5957497a4d475a6b4d6d45784c6d52765933673d&fich=16c9fdf9-4d74-42b8-bdf2-2edab30fd2a1.docx&Inline=true

        🟢 Aprovado

        🗳️ Votação na generalidade (2024-04-24):
        👍 PS, BE, PCP, L, PAN
        🤷 CH, IL
        👎 PSD, CDS-PP
        &in_reply_to_id={approved_thread_id}&visibility=unlisted&language=pt"""
    )
    assert unquote_plus(status_requests[2].body) == dedent(
        f"""\
        status=🔴 Rejeitadas - Votações na Assembleia da República (entre 2024-04-19 e 2024-04-19)

        Veja as votações individuais nas respostas 🧵
        &language=pt"""
    )
    assert unquote_plus(status_requests[3].body) == dedent(
        f"""\
        status=@{user_name} 📝️️ Constituição de uma comissão de inquérito parlamentar ao processo de alteração da propriedade do Global Media Group envolvendo o World Opportunity Fund, Lda.
        🔗 Inquérito Parlamentar (PAN) - http://app.parlamento.pt/webutils/docs/doc.pdf?path=6148523063484d364c793968636d356c6443397a6158526c63793959566b6c4d5a5763765247396a6457316c626e527663306c7561574e7059585270646d45765a4446694d546c684e3251745954686c5a6930305a4745784c54686a5a4755744e6d526a4d544d314f544268596a646a4c6d52765933673d&fich=d1b19a7d-a8ef-4da1-8cde-6dc13590ab7c.docx&Inline=true

        🔴 Rejeitado

        🗳️ Votação Deliberação (2024-04-19):
        👍 IL, BE, PCP, L, PAN
        🤷 CH
        👎 PSD, PS, CDS-PP
        &in_reply_to_id={rejected_thread_id}&visibility=unlisted&language=pt"""
    )

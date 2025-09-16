import json
import pytest
from textwrap import dedent
from urllib.parse import unquote_plus

from votacoes_assembleia_da_republica.update_account import update, render_vote, StateStorage
from votacoes_assembleia_da_republica.fetch_votes import JSON_URIS
from votacoes_assembleia_da_republica.state_storage import StateStorage

# --- Consolidated Fixtures ---

@pytest.fixture(autouse=True)
def stub_env(monkeypatch):
    monkeypatch.setenv('DEBUG_MODE', 'false')
    monkeypatch.setenv('MASTODON_API_BASE_URL', 'https://masto.pt')
    monkeypatch.setenv('GH_VARIABLE_UPDATE_TOKEN', 'gh_token')
    monkeypatch.setenv('REPO_OWNER', 'owner')
    monkeypatch.setenv('REPO_PATH', 'owner/repo')
    monkeypatch.setenv('OVERRIDE_TOO_MANY_NEW_VOTES_ALLOW_AFTER_ISO_DATE', '2024-04-01')
    monkeypatch.setenv('OVERRIDE_TOO_MANY_NEW_VOTES_CHECK', 'true')

@pytest.fixture(autouse=True)
def stub_github_get(requests_mock):
    requests_mock.get(StateStorage('XVI').gh_variable_url, status_code=200, json={ "name": "STATE_XVI", "updated_at": "2025-09-16T09:12:30Z", "value": {} })
    requests_mock.get(StateStorage('XVII').gh_variable_url, status_code=200, json={ "name": "STATE_XVII", "updated_at": "2025-09-16T09:12:30Z", "value": {} })

@pytest.fixture(autouse=True)
def stub_github_patch(requests_mock):
    requests_mock.patch(StateStorage('XVI').gh_variable_url, status_code=200, text='{}')
    requests_mock.patch(StateStorage('XVII').gh_variable_url, status_code=200, text='{}')

@pytest.fixture
def mastodon_account():
    return {'id': 1, 'acct': 'user@server.com'}

@pytest.fixture
def stub_mastodon_api(requests_mock, mastodon_account):
    requests_mock.get('https://masto.pt/api/v1/instance', status_code=200)
    requests_mock.get('https://masto.pt/api/v1/accounts/verify_credentials', status_code=200, json=mastodon_account)

# --- Tests ---

def test_update_doesnt_crash_if_there_are_no_votes(requests_mock, tmp_path):
    with open('tests/files/legislatures/empty_example.json', 'r') as legislature:
        requests_mock.get(JSON_URIS['XVII'], text=legislature.read())
    update('XVII', tmp_path / 'state.json')
    assert requests_mock.called
    assert requests_mock.call_count == 3  # GET to parliament + GET to GitHub + PATCH to GitHub

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

def test_update_still_tries_to_save_state_if_a_post_errors_out(requests_mock, tmp_path, stub_mastodon_api, mastodon_account):
    with open('tests/files/legislatures/minimal_example_approved_and_rejected.json', 'r') as legislature:
        requests_mock.get(JSON_URIS['XVII'], text=legislature.read())
    requests_mock.patch(StateStorage('XVII').gh_variable_url, status_code=200, text='{}')
    requests_mock.post('https://masto.pt/api/v1/statuses', [
        {'json': { 'id': 1, 'account': mastodon_account, 'mentions': []}},
        {'status_code': 422, 'text': 'Validation failed: Text limite de caracter excedeu 500'},
        {'json': { 'id': 2, 'account': mastodon_account, 'mentions': []}},
        {'json': { 'id': 126516, 'account': mastodon_account, 'mentions': []}},
    ])
    state_file_path = tmp_path / 'state.json'
    update('XVII', state_file_path)
    assert requests_mock.called
    assert all(request.hostname in ['app.parlamento.pt', 'masto.pt', 'api.github.com'] for request in requests_mock.request_history)
    assert requests_mock.call_count == 9

    for request in requests_mock.request_history:
        if request.url == StateStorage('XVII').gh_variable_url and request.method == 'PATCH':
            assert request.json() == { 'value': json.dumps({ '126516': 'errored', '126496': 'published' }) }

def test_update_makes_no_mastodon_requests_when_debug_mode_is_enabled(requests_mock, tmp_path, monkeypatch):
    monkeypatch.setenv('DEBUG_MODE', 'true')
    with open('tests/files/legislatures/minimal_example_approved_and_rejected.json', 'r') as legislature:
        requests_mock.get(JSON_URIS['XVII'], text=legislature.read())
    update('XVII', tmp_path / 'state.json')
    assert requests_mock.called
    assert all(request.hostname == 'app.parlamento.pt' for request in requests_mock.request_history)
    assert requests_mock.call_count == 1

def test_update_creates_one_thread_if_there_are_only_votes_with_one_result(requests_mock, tmp_path, stub_mastodon_api, mastodon_account):
    with open('tests/files/legislatures/minimal_example.json', 'r') as legislature:
        requests_mock.get(JSON_URIS['XVII'], text=legislature.read())
    requests_mock.patch(StateStorage('XVII').gh_variable_url, status_code=200, text='{}')
    thread_id = 1
    requests_mock.post('https://masto.pt/api/v1/statuses', json = { 'id': thread_id, 'account': mastodon_account, 'mentions': []})
    update('XVII', tmp_path / 'state.json')
    assert requests_mock.called
    assert all(request.hostname in ['app.parlamento.pt', 'masto.pt', 'api.github.com'] for request in requests_mock.request_history)
    assert requests_mock.call_count == 7
    status_requests = [request for request in requests_mock.request_history if request.url == 'https://masto.pt/api/v1/statuses']
    assert unquote_plus(status_requests[0].body) == dedent(
        f"""\
        status=🔴 Rejeitadas - Votações na Assembleia da República (entre 2024-04-19 e 2024-04-19)

        Veja as votações individuais nas respostas 🧵
        &language=pt"""
    )
    assert unquote_plus(status_requests[1].body) == dedent(
        f"""\
        status=@{mastodon_account['acct']} 📝️️ Constituição de uma comissão de inquérito parlamentar ao processo de alteração da propriedade do Global Media Group envolvendo o World Opportunity Fund, Lda.
        🔗 Inquérito Parlamentar (PAN) - http://app.parlamento.pt/webutils/docs/doc.pdf?path=6148523063484d364c793968636d356c6443397a6158526c63793959566b6c4a5447566e4c305276593356745a57353062334e4a626d6c6a6157463061585a684c7a59314d6a597a4f5459354c5456694d3259744e445579596931684d44426d4c5441334e6a6b78597a63324d5445325969356b62324e34&fich=d1b19a7d-a8ef-4da1-8cde-6dc13590ab7c.docx&Inline=true

        🔴 Rejeitado

        🗳️ Votação Deliberação (2024-04-19):
        👍 IL, BE, PCP, L, PAN
        🤷 CH
        👎 PSD, PS, CDS-PP
        &in_reply_to_id={thread_id}&visibility=unlisted&language=pt"""
    )

def test_update_creates_two_threads_if_there_both_approved_and_rejected_votes(requests_mock, tmp_path, stub_mastodon_api, mastodon_account):
    with open('tests/files/legislatures/minimal_example_approved_and_rejected.json', 'r') as legislature:
        requests_mock.get(JSON_URIS['XVII'], text=legislature.read())
    requests_mock.patch(StateStorage('XVII').gh_variable_url, status_code=200, text='{}')
    approved_thread_id = 1
    rejected_thread_id = 2
    requests_mock.post('https://masto.pt/api/v1/statuses', [
        { 'json': { 'id': approved_thread_id, 'account': mastodon_account, 'mentions': [] } },
        { 'json': { 'id': rejected_thread_id, 'account': mastodon_account, 'mentions': [] } },
    ])
    update('XVII', tmp_path / 'state.json')
    assert requests_mock.called
    assert all(request.hostname in ['app.parlamento.pt', 'masto.pt', 'api.github.com'] for request in requests_mock.request_history)
    assert requests_mock.call_count == 9
    status_requests = [request for request in requests_mock.request_history if request.url == 'https://masto.pt/api/v1/statuses']
    assert unquote_plus(status_requests[0].body) == dedent(
        f"""\
        status=🟢 Aprovadas - Votações na Assembleia da República (entre 2024-04-24 e 2024-04-24)

        Veja as votações individuais nas respostas 🧵
        &language=pt"""
    )
    assert unquote_plus(status_requests[1].body) == dedent(
        f"""\
        status=@{mastodon_account['acct']} 📝️️ Altera o Código do Imposto sobre o Rendimento das Pessoas Singulares
        🔗 Projeto de Lei (PS) - http://app.parlamento.pt/webutils/docs/doc.pdf?path=6148523063484d364c793968636d356c6443397a6158526c63793959566b6c4a5447566e4c305276593356745a57353062334e4a626d6c6a6157463061585a684c7a59314d6a597a4f5459354c5456694d3259744e445579596931684d44426d4c5441334e6a6b78597a63324d5445325969356b62324e34&fich=16c9fdf9-4d74-42b8-bdf2-2edab30fd2a1.docx&Inline=true

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
        status=@{mastodon_account['acct']} 📝️️ Constituição de uma comissão de inquérito parlamentar ao processo de alteração da propriedade do Global Media Group envolvendo o World Opportunity Fund, Lda.
        🔗 Inquérito Parlamentar (PAN) - http://app.parlamento.pt/webutils/docs/doc.pdf?path=6148523063484d364c793968636d356c6443397a6158526c63793959566b6c4a5447566e4c305276593356745a57353062334e4a626d6c6a6157463061585a684c7a59314d6a597a4f5459354c5456694d3259744e445579596931684d44426d4c5441334e6a6b78597a63324d5445325969356b62324e34&fich=d1b19a7d-a8ef-4da1-8cde-6dc13590ab7c.docx&Inline=true

        🔴 Rejeitado

        🗳️ Votação Deliberação (2024-04-19):
        👍 IL, BE, PCP, L, PAN
        🤷 CH
        👎 PSD, PS, CDS-PP
        &in_reply_to_id={rejected_thread_id}&visibility=unlisted&language=pt"""
    )

def test_update_posts_multiple_approved_and_rejected_votes_as_threaded_replies(requests_mock, tmp_path, stub_mastodon_api, mastodon_account):
    """
    Test that multiple approved and rejected votes are posted as replies to the correct threads, with correct in_reply_to_id.
    """
    with open('tests/files/legislatures/multiple_approved_sorted.json', 'r') as legislature:
        requests_mock.get(JSON_URIS['XVII'], text=legislature.read())
    requests_mock.patch(StateStorage('XVII').gh_variable_url, status_code=200, text='{}')
    approved_thread_id = 1
    rejected_thread_id = 2
    requests_mock.post('https://masto.pt/api/v1/statuses', [
        { 'json': { 'id': approved_thread_id, 'account': mastodon_account, 'mentions': [] } },
        { 'json': { 'id': 200001, 'account': mastodon_account, 'mentions': [] } },
        { 'json': { 'id': 200002, 'account': mastodon_account, 'mentions': [] } },
        { 'json': { 'id': rejected_thread_id, 'account': mastodon_account, 'mentions': [] } },
        { 'json': { 'id': 200003, 'account': mastodon_account, 'mentions': [] } },
    ])
    update('XVII', tmp_path / 'state.json')
    status_requests = [r for r in requests_mock.request_history if r.url == 'https://masto.pt/api/v1/statuses']
    # First post is the approved thread starter
    assert 'status=' in unquote_plus(status_requests[0].body)
    # Next two posts should be approved replies with correct in_reply_to_id
    for req in status_requests[1:3]:
        body = unquote_plus(req.body)
        assert f'&in_reply_to_id={approved_thread_id}' in body, f"Missing correct in_reply_to_id for approved in: {body}"
    # Fourth post is the rejected thread starter
    assert 'status=' in unquote_plus(status_requests[3].body)
    # Fifth post should be rejected reply with correct in_reply_to_id
    body = unquote_plus(status_requests[4].body)
    assert f'&in_reply_to_id={rejected_thread_id}' in body, f"Missing correct in_reply_to_id for rejected in: {body}"

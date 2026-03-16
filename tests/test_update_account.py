import pytest
from textwrap import dedent
from urllib.parse import unquote_plus

from votacoes_assembleia_da_republica.update_account import update, render_vote
from votacoes_assembleia_da_republica.fetch_votes import JSON_URIS
from votacoes_assembleia_da_republica.state_storage import StateStorage, _decompress_state

# --- Consolidated Fixtures ---


@pytest.fixture(autouse=True)
def stub_env(monkeypatch):
    monkeypatch.setenv("DEBUG_MODE", "false")
    monkeypatch.setenv("MASTODON_API_BASE_URL", "https://masto.pt")
    monkeypatch.setenv("GH_VARIABLE_UPDATE_TOKEN", "gh_token")
    monkeypatch.setenv("REPO_OWNER", "owner")
    monkeypatch.setenv("REPO_PATH", "owner/repo")
    monkeypatch.setenv("OVERRIDE_UNSAFE_STATE_SKIP_POSTS_BEFORE_ISO_DATE", "2024-04-01")
    monkeypatch.setenv("OVERRIDE_UNSAFE_STATE_CHECK", "true")


@pytest.fixture(autouse=True)
def stub_github_get(requests_mock):
    requests_mock.get(StateStorage("XVI").gh_variable_url, status_code=200, json={"name": "STATE_XVI", "updated_at": "2025-09-16T09:12:30Z", "value": "{}"})
    requests_mock.get(StateStorage("XVII").gh_variable_url, status_code=200, json={"name": "STATE_XVII", "updated_at": "2025-09-16T09:12:30Z", "value": "{}"})
    requests_mock.get(StateStorage("XVI").last_post_id_variable_url, status_code=404)
    requests_mock.get(StateStorage("XVII").last_post_id_variable_url, status_code=404)


@pytest.fixture(autouse=True)
def stub_github_patch(requests_mock):
    requests_mock.patch(StateStorage("XVI").gh_variable_url, status_code=204)
    requests_mock.patch(StateStorage("XVII").gh_variable_url, status_code=204)
    requests_mock.patch(StateStorage("XVI").last_post_id_variable_url, status_code=204)
    requests_mock.patch(StateStorage("XVII").last_post_id_variable_url, status_code=204)


@pytest.fixture
def mastodon_account():
    return {"id": 1, "acct": "user@server.com"}


@pytest.fixture
def stub_mastodon_api(requests_mock, mastodon_account):
    requests_mock.get("https://masto.pt/api/v1/instance", status_code=200)
    requests_mock.get("https://masto.pt/api/v1/accounts/verify_credentials", status_code=200, json=mastodon_account)


# --- Tests ---


def test_update_with_local_state_makes_no_github_requests(requests_mock, tmp_path, stub_mastodon_api, mastodon_account):
    with open("tests/files/legislatures/minimal_example.json", "r") as legislature:
        requests_mock.get(JSON_URIS["XVII"], text=legislature.read())
    requests_mock.post("https://masto.pt/api/v1/statuses", json={"id": 9001, "account": mastodon_account, "mentions": []})
    update("XVII", tmp_path / "state.json")
    assert all(request.hostname != "api.github.com" for request in requests_mock.request_history)


def test_update_does_not_repost_votes_already_in_state(requests_mock, tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text('{"126496": "published"}')
    with open("tests/files/legislatures/minimal_example.json", "r") as legislature:
        requests_mock.get(JSON_URIS["XVII"], text=legislature.read())
    update("XVII", state_file)
    assert not any(r.url == "https://masto.pt/api/v1/statuses" for r in requests_mock.request_history)


def test_update_aborts_if_too_many_new_votes_are_detected(requests_mock, tmp_path, monkeypatch):
    monkeypatch.setenv("OVERRIDE_UNSAFE_STATE_CHECK", "false")
    initiatives = [
        {
            "IniDescTipo": "Projeto de Lei",
            "IniTipo": "P",
            "IniTitulo": f"Vote {i}",
            "IniLinkTexto": "http://example.com",
            "IniAutorGruposParlamentares": None,
            "IniEventos": [{"Fase": "Votação final global", "Votacao": [{"id": str(i), "data": "2024-04-02", "resultado": "Aprovado", "detalhe": "unanime"}]}],
            "IniNr": str(i),
        }
        for i in range(101)
    ]
    requests_mock.get(JSON_URIS["XVII"], json=initiatives)
    with pytest.raises(AssertionError, match="state might have been lost"):
        update("XVII", tmp_path / "state.json")


def test_update_doesnt_crash_if_there_are_no_votes(requests_mock, tmp_path):
    with open("tests/files/legislatures/empty_example.json", "r") as legislature:
        requests_mock.get(JSON_URIS["XVII"], text=legislature.read())
    update("XVII", tmp_path / "state.json", use_github=True)
    assert requests_mock.called
    assert requests_mock.call_count == 3  # GET to parliament + GET state + PATCH state


def test_render_vote_cuts_down_text_down_to_the_500_char_limit():
    test_vote = {
        "vote_id": "12345",
        "result": "Rejeitado",
        "vote_detail": "unanime",
        "date": "2024-04-10",
        "authors": ["author 1", "author 2"],
        "initiative_type": "Projeto de Lei",
        "title": 1000 * "A",
        "phase": "Entrada",
        "initiative_uri": "http://app.parlamento.pt/webutils/docs/doc.pdf?path=6148523063484d364c793968636d356c6443397a6158526c63793959566b6c4d5a5763765247396a6457316c626e527663306c7561574e7059585270646d4576597a466b5a6d453459544d744d475a685a5330304d32557a4c5749325a6d4d744e6a6b78596a55794d5449304f47517a4c6d52765933673d&fich=c1dfa8a3-0fae-43e3-b6fc-691b521248d3.docx&Inline=true",
    }
    assert len(render_vote(test_vote)) - len(test_vote["initiative_uri"]) + 23 == 500


def test_update_still_tries_to_save_state_if_a_post_errors_out(requests_mock, tmp_path, stub_mastodon_api, mastodon_account):
    with open("tests/files/legislatures/minimal_example_approved_and_rejected.json", "r") as legislature:
        requests_mock.get(JSON_URIS["XVII"], text=legislature.read())
    requests_mock.patch(StateStorage("XVII").gh_variable_url, status_code=204)
    requests_mock.post(
        "https://masto.pt/api/v1/statuses",
        [
            {"json": {"id": 1, "account": mastodon_account, "mentions": []}},
            {"status_code": 422, "text": "Validation failed: Text limite de caracter excedeu 500"},
            {"json": {"id": 2, "account": mastodon_account, "mentions": []}},
            {"json": {"id": 126516, "account": mastodon_account, "mentions": []}},
        ],
    )
    state_file_path = tmp_path / "state.json"
    update("XVII", state_file_path, use_github=True)
    assert requests_mock.called
    assert all(request.hostname in ["app.parlamento.pt", "masto.pt", "api.github.com"] for request in requests_mock.request_history)
    assert requests_mock.call_count == 10

    for request in requests_mock.request_history:
        if request.url == StateStorage("XVII").gh_variable_url and request.method == "PATCH":
            assert _decompress_state(request.json()["value"]) == {"126516": "errored", "126496": "published"}


def test_update_makes_no_write_requests_when_debug_mode_is_enabled(requests_mock, tmp_path, monkeypatch):
    monkeypatch.setenv("DEBUG_MODE", "true")
    with open("tests/files/legislatures/minimal_example_approved_and_rejected.json", "r") as legislature:
        requests_mock.get(JSON_URIS["XVII"], text=legislature.read())
    update("XVII", tmp_path / "state.json", use_github=True)
    assert requests_mock.called
    assert not any(r.method in ("POST", "PATCH") for r in requests_mock.request_history)


def test_update_creates_one_thread_if_there_are_only_votes_with_one_result(requests_mock, tmp_path, stub_mastodon_api, mastodon_account):
    with open("tests/files/legislatures/minimal_example.json", "r") as legislature:
        requests_mock.get(JSON_URIS["XVII"], text=legislature.read())
    requests_mock.patch(StateStorage("XVII").gh_variable_url, status_code=204)
    thread_id = 1
    requests_mock.post("https://masto.pt/api/v1/statuses", json={"id": thread_id, "account": mastodon_account, "mentions": []})
    update("XVII", tmp_path / "state.json", use_github=True)
    assert requests_mock.called
    assert all(request.hostname in ["app.parlamento.pt", "masto.pt", "api.github.com"] for request in requests_mock.request_history)
    assert requests_mock.call_count == 8
    status_requests = [request for request in requests_mock.request_history if request.url == "https://masto.pt/api/v1/statuses"]
    assert unquote_plus(status_requests[0].body) == dedent(
        """\
        status=🔴 Rejeitadas - Votações na Assembleia da República (entre 2024-04-19 e 2024-04-19)

        Veja as votações individuais nas respostas 🧵
        &language=pt"""
    )
    assert unquote_plus(status_requests[1].body) == dedent(
        f"""\
        status=📝️️ Constituição de uma comissão de inquérito parlamentar ao processo de alteração da propriedade do Global Media Group envolvendo o World Opportunity Fund, Lda.
        🔗 Inquérito Parlamentar (PAN) - http://app.parlamento.pt/webutils/docs/doc.pdf?path=6148523063484d364c793968636d356c6443397a6158526c63793959566b6c4a5447566e4c305276593356745a57353062334e4a626d6c6a6157463061585a684c7a59314d6a597a4f5459354c5456694d3259744e445579596931684d44426d4c5441334e6a6b78597a63324d5445325969356b62324e34&fich=d1b19a7d-a8ef-4da1-8cde-6dc13590ab7c.docx&Inline=true

        🔴 Rejeitado

        🗳️ Votação Deliberação (2024-04-19):
        👍 IL, BE, PCP, L, PAN
        🤷 CH
        👎 PSD, PS, CDS-PP
        &in_reply_to_id={thread_id}&visibility=unlisted&language=pt"""
    )


def test_update_creates_two_threads_if_there_both_approved_and_rejected_votes(requests_mock, tmp_path, stub_mastodon_api, mastodon_account):
    with open("tests/files/legislatures/minimal_example_approved_and_rejected.json", "r") as legislature:
        requests_mock.get(JSON_URIS["XVII"], text=legislature.read())
    requests_mock.patch(StateStorage("XVII").gh_variable_url, status_code=204)
    approved_thread_id = 1
    rejected_thread_id = 2
    requests_mock.post(
        "https://masto.pt/api/v1/statuses",
        [
            {"json": {"id": approved_thread_id, "account": mastodon_account, "mentions": []}},
            {"json": {"id": rejected_thread_id, "account": mastodon_account, "mentions": []}},
        ],
    )
    update("XVII", tmp_path / "state.json", use_github=True)
    assert requests_mock.called
    assert all(request.hostname in ["app.parlamento.pt", "masto.pt", "api.github.com"] for request in requests_mock.request_history)
    assert requests_mock.call_count == 10
    status_requests = [request for request in requests_mock.request_history if request.url == "https://masto.pt/api/v1/statuses"]
    assert unquote_plus(status_requests[0].body) == dedent(
        """\
        status=🟢 Aprovadas - Votações na Assembleia da República (entre 2024-04-24 e 2024-04-24)

        Veja as votações individuais nas respostas 🧵
        &language=pt"""
    )
    assert unquote_plus(status_requests[1].body) == dedent(
        f"""\
        status=📝️️ Altera o Código do Imposto sobre o Rendimento das Pessoas Singulares
        🔗 Projeto de Lei (PS) - http://app.parlamento.pt/webutils/docs/doc.pdf?path=6148523063484d364c793968636d356c6443397a6158526c63793959566b6c4a5447566e4c305276593356745a57353062334e4a626d6c6a6157463061585a684c7a59314d6a597a4f5459354c5456694d3259744e445579596931684d44426d4c5441334e6a6b78597a63324d5445325969356b62324e34&fich=16c9fdf9-4d74-42b8-bdf2-2edab30fd2a1.docx&Inline=true

        🟢 Aprovado

        🗳️ Votação na generalidade (2024-04-24):
        👍 PS, BE, PCP, L, PAN
        🤷 CH, IL
        👎 PSD, CDS-PP
        &in_reply_to_id={approved_thread_id}&visibility=unlisted&language=pt"""
    )
    assert unquote_plus(status_requests[2].body) == dedent(
        """\
        status=🔴 Rejeitadas - Votações na Assembleia da República (entre 2024-04-19 e 2024-04-19)

        Veja as votações individuais nas respostas 🧵
        &language=pt"""
    )
    assert unquote_plus(status_requests[3].body) == dedent(
        f"""\
        status=📝️️ Constituição de uma comissão de inquérito parlamentar ao processo de alteração da propriedade do Global Media Group envolvendo o World Opportunity Fund, Lda.
        🔗 Inquérito Parlamentar (PAN) - http://app.parlamento.pt/webutils/docs/doc.pdf?path=6148523063484d364c793968636d356c6443397a6158526c63793959566b6c4a5447566e4c305276593356745a57353062334e4a626d6c6a6157463061585a684c7a59314d6a597a4f5459354c5456694d3259744e445579596931684d44426d4c5441334e6a6b78597a63324d5445325969356b62324e34&fich=d1b19a7d-a8ef-4da1-8cde-6dc13590ab7c.docx&Inline=true

        🔴 Rejeitado

        🗳️ Votação Deliberação (2024-04-19):
        👍 IL, BE, PCP, L, PAN
        🤷 CH
        👎 PSD, PS, CDS-PP
        &in_reply_to_id={rejected_thread_id}&visibility=unlisted&language=pt"""
    )


def test_update_aborts_if_last_post_id_does_not_match(requests_mock, tmp_path, monkeypatch, stub_mastodon_api, mastodon_account):
    monkeypatch.setenv("OVERRIDE_UNSAFE_STATE_CHECK", "false")
    requests_mock.get(StateStorage("XVII").last_post_id_variable_url, status_code=200, json={"value": "1234"})
    requests_mock.get("https://masto.pt/api/v1/accounts/1/statuses", json=[{"id": "9000999"}])

    with open("tests/files/legislatures/minimal_example.json", "r") as legislature:
        requests_mock.get(JSON_URIS["XVII"], text=legislature.read())

    with pytest.raises(AssertionError, match="Last post ID mismatch"):
        update("XVII", tmp_path / "state.json", use_github=True)

    assert not any(r.url == "https://masto.pt/api/v1/statuses" for r in requests_mock.request_history)


def test_update_proceeds_if_last_post_id_matches(requests_mock, tmp_path, monkeypatch, stub_mastodon_api, mastodon_account):
    monkeypatch.setenv("OVERRIDE_UNSAFE_STATE_CHECK", "false")
    requests_mock.get(StateStorage("XVII").last_post_id_variable_url, status_code=200, json={"value": "9000001"})
    requests_mock.get("https://masto.pt/api/v1/accounts/1/statuses", json=[{"id": "9000001"}])

    with open("tests/files/legislatures/minimal_example.json", "r") as legislature:
        requests_mock.get(JSON_URIS["XVII"], text=legislature.read())
    requests_mock.post("https://masto.pt/api/v1/statuses", json={"id": 9000002, "account": mastodon_account, "mentions": []})
    update("XVII", tmp_path / "state.json", use_github=True)

    assert any(r.url == "https://masto.pt/api/v1/statuses" for r in requests_mock.request_history)
    last_post_id_patches = [r for r in requests_mock.request_history if r.url == StateStorage("XVII").last_post_id_variable_url and r.method == "PATCH"]
    assert len(last_post_id_patches) == 1
    assert last_post_id_patches[0].json()["value"] == "9000002"


def test_update_skips_staleness_check_if_no_last_post_id_stored(requests_mock, tmp_path, stub_mastodon_api, mastodon_account):
    # LAST_POST_ID returns 404 (autouse fixture) — no previous post recorded, so no check needed
    with open("tests/files/legislatures/minimal_example.json", "r") as legislature:
        requests_mock.get(JSON_URIS["XVII"], text=legislature.read())

    requests_mock.post("https://masto.pt/api/v1/statuses", json={"id": 9001, "account": mastodon_account, "mentions": []})
    update("XVII", tmp_path / "state.json", use_github=True)

    assert any(r.url == "https://masto.pt/api/v1/statuses" for r in requests_mock.request_history)


def test_update_does_not_update_last_post_id_if_all_posts_error(requests_mock, tmp_path, stub_mastodon_api, mastodon_account):
    with open("tests/files/legislatures/minimal_example.json", "r") as legislature:
        requests_mock.get(JSON_URIS["XVII"], text=legislature.read())

    requests_mock.post(
        "https://masto.pt/api/v1/statuses",
        [
            {"json": {"id": 1, "account": mastodon_account, "mentions": []}},  # thread start succeeds
            {"status_code": 422, "text": "Validation failed: Text limite de caracter excedeu 500"},  # vote errors
        ],
    )
    update("XVII", tmp_path / "state.json", use_github=True)

    assert not any(r.url == StateStorage("XVII").last_post_id_variable_url and r.method == "PATCH" for r in requests_mock.request_history)


def test_update_sets_last_post_id_to_last_successful_post(requests_mock, tmp_path, stub_mastodon_api, mastodon_account):
    with open("tests/files/legislatures/minimal_example_approved_and_rejected.json", "r") as legislature:
        requests_mock.get(JSON_URIS["XVII"], text=legislature.read())
    requests_mock.post(
        "https://masto.pt/api/v1/statuses",
        [
            {"json": {"id": 1, "account": mastodon_account, "mentions": []}},  # approved thread start
            {"status_code": 422, "text": "Validation failed: Text limite de caracter excedeu 500"},  # approved vote (126516) errors
            {"json": {"id": 2, "account": mastodon_account, "mentions": []}},  # rejected thread start
            {"json": {"id": 9000042, "account": mastodon_account, "mentions": []}},  # rejected vote (126496) succeeds
        ],
    )
    update("XVII", tmp_path / "state.json", use_github=True)
    last_post_id_patches = [r for r in requests_mock.request_history if r.url == StateStorage("XVII").last_post_id_variable_url and r.method == "PATCH"]
    assert len(last_post_id_patches) == 1
    assert last_post_id_patches[0].json()["value"] == "9000042"


def test_update_posts_multiple_approved_and_rejected_votes_as_threaded_replies(requests_mock, tmp_path, stub_mastodon_api, mastodon_account):
    """
    Test that multiple approved and rejected votes are posted as replies to the correct threads, with correct in_reply_to_id.
    """
    with open("tests/files/legislatures/multiple_approved_sorted.json", "r") as legislature:
        requests_mock.get(JSON_URIS["XVII"], text=legislature.read())
    requests_mock.patch(StateStorage("XVII").gh_variable_url, status_code=204)
    approved_thread_id = 1
    rejected_thread_id = 2
    requests_mock.post(
        "https://masto.pt/api/v1/statuses",
        [
            {"json": {"id": approved_thread_id, "account": mastodon_account, "mentions": []}},
            {"json": {"id": 200001, "account": mastodon_account, "mentions": []}},
            {"json": {"id": 200002, "account": mastodon_account, "mentions": []}},
            {"json": {"id": rejected_thread_id, "account": mastodon_account, "mentions": []}},
            {"json": {"id": 200003, "account": mastodon_account, "mentions": []}},
        ],
    )
    update("XVII", tmp_path / "state.json", use_github=True)
    status_requests = [r for r in requests_mock.request_history if r.url == "https://masto.pt/api/v1/statuses"]
    # First post is the approved thread starter
    assert "status=" in unquote_plus(status_requests[0].body)
    # Next two posts should be approved replies with correct in_reply_to_id
    for req in status_requests[1:3]:
        body = unquote_plus(req.body)
        assert f"&in_reply_to_id={approved_thread_id}" in body, f"Missing correct in_reply_to_id for approved in: {body}"
    # Fourth post is the rejected thread starter
    assert "status=" in unquote_plus(status_requests[3].body)
    # Fifth post should be rejected reply with correct in_reply_to_id
    body = unquote_plus(status_requests[4].body)
    assert f"&in_reply_to_id={rejected_thread_id}" in body, f"Missing correct in_reply_to_id for rejected in: {body}"

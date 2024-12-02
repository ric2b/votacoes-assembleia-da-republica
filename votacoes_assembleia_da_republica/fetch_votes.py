import requests
from bs4 import BeautifulSoup

# full list https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx
JSON_URIS = {
    'XVI': 'https://app.parlamento.pt/webutils/docs/doc.txt?path=p%2bSA2AT%2fyt2iwr8bwKM9dJ8sza2EknnElLNpyhYHRVrtIPiG5z0I6gGOdIl1oXFhqjoubuAuET0Zgm9uEI4rI%2bNvpyKFqmN1my4x3fv98P%2bj5Mn%2bSR76ofKRj0vdiGGF8qfzfW5sKgM3%2fpbycpdVyQ%2ffPzSQ5%2fK%2bn7I1Zf60qUGKlUd34Semm%2fxaK2vteEQ2ZMeST6X%2fRTMsO3siuJxiN%2br3nOg8sWY8ig7BgP8nH5hMwOzDV4nmuQ3kDAwNX1WOqq6x0dKkRRBtWrWasxookYPf9GstdSROcBA%2bIijpMtmhJ8ncoQQxBMUMCM512sL0kJ6Jtl4V0tMnVv4NkiHAzkSH1TKcASxH%2b%2b4pdV8aFiMATzcTV5RT%2fCK4UfYyM%2bYn&fich=IniciativasXVI_json.txt&Inline=true',
}

def fetch_votes_for_legislature(legislature):
    initiatives = fetch_initiatives_for_legislature(legislature)

    print('parsing votes')
    # {'Requerimento de adiamento de Votação (Generalidade)', 'Requerimento', 'Requerimento de adiamento de Votação', 'Requerimento dispensa do prazo previsto Artº 157 RAR', 'Votação final global', 'Requerimento avocação plenário', 'Votação na especialidade', 'Votação Deliberação', 'Votação do recurso da decisão do PAR', 'Confirmação do decreto', 'Votação na generalidade', 'Requerimento Baixa Comissão sem Votação (Generalidade)', 'Votação do parecer recurso de admissibilidade', 'Votação novo decreto'}

    return parse_initiatives(initiatives)

def fetch_initiatives_for_legislature(legislature):
    return requests.get(JSON_URIS[legislature]).json()

def parse_vote(raw_vote) -> str | dict[str, list[str]]:
    if raw_vote['vote_detail'] == 'unanime':
        vote_detail = 'unanime'
    else:
        sections = dict(x.split(':') for x in raw_vote['vote_detail'].split('<BR>'))

        for k, v in sections.items():
            ctext = BeautifulSoup(v, 'lxml')
            sections[k] = list(map(lambda s: s.strip(), ctext.get_text().strip().split(",")))

        vote_detail = {
            'in_favour': sections.get('A Favor', []),
            'against': sections.get('Contra', []),
            'abstained': sections.get('Abstenção', []),
            'absent': sections.get('Ausência', []),
        }

    return {
        'vote_id': raw_vote['vote_id'],
        'result': raw_vote['result'],
        'vote_detail': vote_detail,
        'date': raw_vote['date'],
        'authors': raw_vote['authors'],
        'initiative_type': raw_vote['initiative_type'],
        'title': raw_vote['title'],
        'phase': raw_vote['phase'],
        'initiative_uri': raw_vote['initiative_uri'],
    }

def list_wrap(raw) -> list:
    return raw if isinstance(raw, list) else [raw]

def parse_authorship(initiative) -> list[str]:
    if not initiative['IniAutorGruposParlamentares']:
        return ['Outro']

    authors = list_wrap(initiative['IniAutorGruposParlamentares'])
    return [author['GP'] for author in authors]

def parse_initiatives(raw_initiatives) -> list[dict]:
    votes = []
    for initiative in raw_initiatives:
        events = list_wrap(initiative['IniEventos'])

        for event in events:
            if event['Votacao']:
                for raw_vote in list_wrap(event['Votacao']):
                    try:
                        vote = {
                            'vote_id': raw_vote['id'],
                            'initiative_type': initiative['IniDescTipo'],
                            'initiative_type_code': initiative['IniTipo'],
                            'title': initiative['IniTitulo'],
                            'initiative_uri': initiative['IniLinkTexto'],
                            'authors': parse_authorship(initiative),
                            'phase': event['Fase'],
                            'date': raw_vote['data'],
                            'result': raw_vote['resultado'],
                            'vote_detail': raw_vote['detalhe'] or raw_vote.get('unanime'),
                        }

                        votes.append(vote)
                    except Exception as e:
                        import pprint
                        print(initiative['IniNr'])
                        pprint.pp(raw_vote)
                        raise e
                        exit()

    return votes

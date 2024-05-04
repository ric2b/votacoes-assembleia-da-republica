import json
import pprint
import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from mastodon import Mastodon
from operator import itemgetter, attrgetter
from string import Template

load_dotenv()
MASTODON_ACCESS_TOKEN = os.environ['MASTODON_ACCESS_TOKEN']
DEBUG_MODE = os.environ.get('DEBUG_MODE', 'false').lower() == 'true'
SKIP_ALL = os.environ.get('SKIP_ALL', 'false').lower() == 'true'

# full list https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx
JSON_URIS = {
    'XVI': 'https://app.parlamento.pt/webutils/docs/doc.txt?path=JIf%2bfNEFTJ3dZjfk2SEgv7akbMN1hBC%2fl88Tim%2bRTzTnLS1tvsCi0B3Lm2ReYXUcazUcPcGvstFujlwAWizrbpdrEV%2fH%2fhIj%2boq49E1lcuhsGcEdXynUiqGK6wHUnTe3CehLsOI3aZj0hvjakE7sD8eDicdNpIuy5Xzd9e2yo6VnmuBjuq1jgLxTZCcBGK3KUc0taNvXf%2b816sIPNUK0K9QJiPgf%2bpXBOM3lZWBKTPlgPciZYyfHaRnuBzll7aLI57H6ADfms%2ffbK3HQlwRzhej64OLMKN8SG%2bJ89HZLGHfdzFBMupBH0czdzcua0A9jgWPVtIhoSbjW5Np5dsPusDHBaW2Zhg2W2rSsbQp9kPA%3d&fich=IniciativasXVI_json.txt&Inline=true',
    'XV': 'https://app.parlamento.pt/webutils/docs/doc.txt?path=9pmNwL6GoXv7I7%2b%2fqIbTfPny7HRpBWiyHiyClKcla8C2sa9EbIgDyIZa9rTsuI6jG3KgMosUtvKl%2fek7BtzUee6kPEU6gITunDOdPb0T7gMnfM5%2bUWWRn6r2t42DSM63%2fJ8az36bpRSJRpyggVhCBBQaOYNMwQPVFMNSkpSUQL2zczuCdhZgMg55hQZ%2fYBmuFwowZHRTHoSMFhd7ILx58tsqdWEWAdDti73T55KxYGPH6u80%2bQVLC9wvYuYm433%2bksaSYCLQ3J%2fUA5OZBrd4ixlscy1B%2b05uflW2PMAzAB8jsVMIoGk97YMNCzkxHccRMsmN2Ge2h6jIbN8uYcpbzRUUR0ImHSj1NHlc4Hq%2bcVc%3d&fich=IniciativasXV_json.txt&Inline=true',
}

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

    def skip_vote(self, vote_id: str) -> None:
        if vote_id not in self.state:
            self.state[vote_id] = 'skipped'

    def is_new_vote(self, vote_id: str) -> bool:
        return vote_id not in self.state

class MastodonClient:
    def __init__(self) -> None:
        self.client = Mastodon(access_token=MASTODON_ACCESS_TOKEN, api_base_url="https://masto.pt")

    def post_vote(self, raw_vote: dict) -> str:
        if DEBUG_MODE:
            print(f'would post vote:')
            print(render_vote(raw_vote))
            print('--------------------')
            return

        vote_id = raw_vote['vote_id']
        self.client.status_post(render_vote(raw_vote), idempotency_key = vote_id)
#         self.client.status_post(render_vote(raw_vote))

def list_wrap(raw) -> list:
    return raw if isinstance(raw, list) else [raw]

def render_vote(vote: dict) -> str:
    with open('vote_status.template', 'r') as toot_template_file:
        toot_template = Template(toot_template_file.read())
        vote_detail = parse_votes(vote['vote_detail'])

        if vote_detail == 'unanime':
            rendered_vote_detail = '🤝 Unânime'
        else:
            with open('vote_detail.template', 'r') as vote_detail_template_file:
                vote_detail_template = Template(vote_detail_template_file.read())
                rendered_vote_detail = vote_detail_template.substitute(
                    in_favour = ', '.join(vote_detail['in_favour']),
                    against = ', '.join(vote_detail['against']),
                    abstained = ', '.join(vote_detail['abstained'] + vote_detail['absent']),
                )

        return toot_template.substitute(
            result = '🟢 Aprovado' if vote['result'] == 'Aprovado' else '🔴 Rejeitado',
            date = vote['date'],
            type = vote['initiative_type'],
            authors = ', '.join(vote['authors']),
            title = vote['title'],
            phase = vote['phase'],
            vote_detail = rendered_vote_detail,
            initiative_uri = vote['initiative_uri'],
        )

def fetch_initiatives_for_legislature(legislature):
    return requests.get(JSON_URIS[legislature]).json()

def parse_votes(raw_votes) -> str | dict[str, list[str]]:
    if raw_votes == 'unanime':
        return 'unanime'

    sections = dict(x.split(':') for x in raw_votes.split('<BR>'))

    for k, v in sections.items():
        ctext = BeautifulSoup(v, 'lxml')
        sections[k] = list(map(lambda s: s.strip(), ctext.get_text().strip().split(",")))

    return {
        'in_favour': sections.get('A Favor', []),
        'against': sections.get('Contra', []),
        'abstained': sections.get('Abstenção', []),
        'absent': sections.get('Ausência', []),
    }

def parse_authorship(initiative) -> list[str]:
    if 'iniAutorGruposParlamentares' not in initiative:
        return ['Outro']

    authors = list_wrap(initiative['iniAutorGruposParlamentares']['pt_gov_ar_objectos_AutoresGruposParlamentaresOut'])
    return [author['GP'] for author in authors]

def parse_initiatives(raw_initiatives) -> list[dict]:
    initiatives = raw_initiatives['ArrayOfPt_gov_ar_objectos_iniciativas_DetalhePesquisaIniciativasOut']['pt_gov_ar_objectos_iniciativas_DetalhePesquisaIniciativasOut']

    votes = []
    for initiative in initiatives:
        events = list_wrap(initiative['iniEventos']['pt_gov_ar_objectos_iniciativas_EventosOut'])

        for event in events:
            try:
                if 'votacao' in event:
                    raw_vote = event['votacao']['pt_gov_ar_objectos_VotacaoOut']

                    vote = {
                        'vote_id': event['oevId'],
                        'initiative_type': initiative['iniDescTipo'],
                        'initiative_type_code': initiative['iniTipo'],
                        'title': initiative['iniTitulo'],
                        'initiative_uri': initiative['iniLinkTexto'],
                        'authors': parse_authorship(initiative),
                        'phase': event['fase'],
                        'date': raw_vote['data'],
                        'result': raw_vote['resultado'],
                        'vote_detail': raw_vote.get('detalhe', raw_vote.get('unanime')),
                    }

                    votes.append(vote)
            except Exception as e:
                import pprint
                pprint.pp(initiative)
                pprint.pp(event)
                print(event)
                raise e
                exit()
    return votes

def filter_new_votes(all_votes, last_posted_oevid):
    sorted_votes = sorted(all_votes, key=itemgetter('oevId'))
    print(list(map(lambda x: x['oevId'], sorted_votes)))
    print(list(map(lambda x: x['data'], sorted_votes)))

    try:
        return [vote for vote in sorted_votes if vote['oevId'] > last_posted_oevid]
    except KeyError as e:
        import pprint
        pprint.pp(all_votes)
        raise e

if __name__ == '__main__':
    with StateStorage() as state:
        print('fetching initiatives')
        initiatives = fetch_initiatives_for_legislature('XVI')

        print('parsing votes')
        # {'Requerimento de adiamento de Votação (Generalidade)', 'Requerimento', 'Requerimento de adiamento de Votação', 'Requerimento dispensa do prazo previsto Artº 157 RAR', 'Votação final global', 'Requerimento avocação plenário', 'Votação na especialidade', 'Votação Deliberação', 'Votação do recurso da decisão do PAR', 'Confirmação do decreto', 'Votação na generalidade', 'Requerimento Baixa Comissão sem Votação (Generalidade)', 'Votação do parecer recurso de admissibilidade', 'Votação novo decreto'}

        votes = parse_initiatives(initiatives)

        if SKIP_ALL:
            print('marking all votes as skipped')
            for vote in votes:
                state.skip_vote(vote['vote_id'])

        new_votes = [vote for vote in votes if state.is_new_vote(vote['vote_id'])]

        if len(new_votes) > 20:
            print(f'Found {len(new_votes)} new votes, state might have been lost, aborting.')
            exit(-1)

        print('posting votes')
        m = MastodonClient()
        for new_vote in sorted(new_votes, key = itemgetter('date')):
            print(f'posting vote {new_vote['vote_id']}')

            m.post_vote(new_vote)
            state.mark_vote_published(new_vote['vote_id'])

    print('done')

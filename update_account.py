import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from mastodon import Mastodon
from operator import itemgetter, attrgetter
from string import Template

load_dotenv()
MASTODON_ACCESS_TOKEN = os.environ['MASTODON_ACCESS_TOKEN']

LAST_POSTED_VOTE_ID_KEY = 'last_posted_oevid'
LAST_SEEN_INITIATIVE_COUNT = 'last_seen_initiative_count'

# full list https://www.parlamento.pt/Cidadania/Paginas/DAIniciativas.aspx
JSON_URIS = {
    'XVI': 'https://app.parlamento.pt/webutils/docs/doc.txt?path=JIf%2bfNEFTJ3dZjfk2SEgv7akbMN1hBC%2fl88Tim%2bRTzTnLS1tvsCi0B3Lm2ReYXUcazUcPcGvstFujlwAWizrbpdrEV%2fH%2fhIj%2boq49E1lcuhsGcEdXynUiqGK6wHUnTe3CehLsOI3aZj0hvjakE7sD8eDicdNpIuy5Xzd9e2yo6VnmuBjuq1jgLxTZCcBGK3KUc0taNvXf%2b816sIPNUK0K9QJiPgf%2bpXBOM3lZWBKTPlgPciZYyfHaRnuBzll7aLI57H6ADfms%2ffbK3HQlwRzhej64OLMKN8SG%2bJ89HZLGHfdzFBMupBH0czdzcua0A9jgWPVtIhoSbjW5Np5dsPusDHBaW2Zhg2W2rSsbQp9kPA%3d&fich=IniciativasXVI_json.txt&Inline=true',
    'XV': 'https://app.parlamento.pt/webutils/docs/doc.txt?path=9pmNwL6GoXv7I7%2b%2fqIbTfPny7HRpBWiyHiyClKcla8C2sa9EbIgDyIZa9rTsuI6jG3KgMosUtvKl%2fek7BtzUee6kPEU6gITunDOdPb0T7gMnfM5%2bUWWRn6r2t42DSM63%2fJ8az36bpRSJRpyggVhCBBQaOYNMwQPVFMNSkpSUQL2zczuCdhZgMg55hQZ%2fYBmuFwowZHRTHoSMFhd7ILx58tsqdWEWAdDti73T55KxYGPH6u80%2bQVLC9wvYuYm433%2bksaSYCLQ3J%2fUA5OZBrd4ixlscy1B%2b05uflW2PMAzAB8jsVMIoGk97YMNCzkxHccRMsmN2Ge2h6jIbN8uYcpbzRUUR0ImHSj1NHlc4Hq%2bcVc%3d&fich=IniciativasXV_json.txt&Inline=true',
}

class MastodonClient:
    def __init__(self) -> None:
        self.client = Mastodon(access_token=MASTODON_ACCESS_TOKEN, api_base_url="https://masto.pt")

    def fetch_fields(self) -> dict[str, str]:
        raw_fields = self.client.me()['fields']
        return { field['name']: field['value'] for field in raw_fields }

    def update_fields(self, fields: dict[str, str]) -> None:
        self.client.account_update_credentials(fields = fields.items())

    def post_vote(self, raw_vote: dict) -> str:
#         import pprint
#         print('posting votes... NOT!')
#         print(render_vote(raw_vote))
#         print('--------------------')
#         return

        vote_id = raw_vote['oevId']
        self.client.status_post(render_vote(raw_vote), idempotency_key = vote_id)

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

def initiatives_count(raw_initiatives) -> int:
    return len(raw_initiatives['ArrayOfPt_gov_ar_objectos_iniciativas_DetalhePesquisaIniciativasOut']['pt_gov_ar_objectos_iniciativas_DetalhePesquisaIniciativasOut'])

def parse_initiatives(raw_initiatives, only_vote_types = ['Votação final global'], from_index = 0) -> list[dict]:
    initiatives = raw_initiatives['ArrayOfPt_gov_ar_objectos_iniciativas_DetalhePesquisaIniciativasOut']['pt_gov_ar_objectos_iniciativas_DetalhePesquisaIniciativasOut']

    votes = []
    for initiative in initiatives[from_index:]:
        events = list_wrap(initiative['iniEventos']['pt_gov_ar_objectos_iniciativas_EventosOut'])

        for event in events:
            try:
                if (event['fase'] in only_vote_types) and ('votacao' in event):
                    raw_vote = event['votacao']['pt_gov_ar_objectos_VotacaoOut']

                    vote = {
                        'oevId': event['oevId'],
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
    print('fetching initiatives')
    initiatives = fetch_initiatives_for_legislature('XVI')

    print('fetching account fields')
    m = MastodonClient()
    account_fields = m.fetch_fields()

    print('parsing votes')
    last_seen_index = account_fields.get(LAST_SEEN_INITIATIVE_COUNT, 1) - 1
    only_vote_types = ['Votação Deliberação', 'Votação na generalidade', 'Votação global', 'Votação final global']

    new_votes = parse_initiatives(initiatives, only_vote_types = only_vote_types, from_index = last_seen_index)

    account_fields[LAST_SEEN_INITIATIVE_COUNT] = initiatives_count(initiatives)

    print('posting votes')
    for new_vote in new_votes:
        print(f'posting vote {new_vote['oevId']}')

        m.post_vote(new_vote)
        account_fields[LAST_POSTED_VOTE_ID_KEY] = new_vote['oevId']

    print(f'updating fields: {account_fields}')
    m.update_fields(account_fields)

    print('done')

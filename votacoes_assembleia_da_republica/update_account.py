import os
from dotenv import load_dotenv
from operator import itemgetter
from string import Template

load_dotenv()

from votacoes_assembleia_da_republica.state_storage import StateStorage
from votacoes_assembleia_da_republica.mastodon_client import MastodonClient
from votacoes_assembleia_da_republica.fetch_votes import fetch_votes_for_legislature, parse_vote

MARK_ALL_AS_PUBLISHED = os.environ.get('MARK_ALL_AS_PUBLISHED', 'false').lower() == 'true'
OVERRIDE_TOO_MANY_NEW_VOTES_CHECK = os.environ.get('OVERRIDE_TOO_MANY_NEW_VOTES_CHECK', 'false').lower() == 'true'

def render_vote(vote: dict) -> str:
    with open('vote_status.template', 'r') as toot_template_file:
        toot_template = Template(toot_template_file.read())

        vote_detail = vote['vote_detail']
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

def update():
    with StateStorage() as state:
            print('fetching votes')
            raw_votes = fetch_votes_for_legislature('XVI')

            if MARK_ALL_AS_PUBLISHED:
                print('marking all votes as published')
                state.state = {}
                for raw_vote in raw_votes:
                    state.mark_vote_published(raw_vote['vote_id'])

            new_votes = [parse_vote(raw_vote) for raw_vote in raw_votes if state.is_new_vote(raw_vote['vote_id'])]

            if len(new_votes) > 100 and not OVERRIDE_TOO_MANY_NEW_VOTES_CHECK:
                print(f'Found {len(new_votes)} new votes, state might have been lost, aborting.')
                exit(-1)

            print('posting votes')
            m = MastodonClient()
            for new_vote in sorted(new_votes, key = itemgetter('date')):
                vote_id = new_vote['vote_id']

                print(f'posting vote {vote_id}')
                m.post_vote(render_vote(new_vote), idempotency_key = vote_id)
                state.mark_vote_published(vote_id)

if __name__ == '__main__':
    update()
    print('done')

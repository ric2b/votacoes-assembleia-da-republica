import os
from dotenv import load_dotenv
from operator import itemgetter
from string import Template

from votacoes_assembleia_da_republica.state_storage import StateStorage
from votacoes_assembleia_da_republica.mastodon_client import MastodonClient
from votacoes_assembleia_da_republica.fetch_votes import fetch_votes_for_legislature, parse_vote

MARK_ALL_AS_PUBLISHED = os.environ.get('MARK_ALL_AS_PUBLISHED', 'false').lower() == 'true'
OVERRIDE_TOO_MANY_NEW_VOTES_CHECK = os.environ.get('OVERRIDE_TOO_MANY_NEW_VOTES_CHECK', 'false').lower() == 'true'

def render_thread(result: str, sorted_new_votes: list[dict]) -> str:
    date_start = sorted_new_votes[0]['date']
    date_end = sorted_new_votes[-1]['date']

    with open('vote_thread.template', 'r') as thread_template_file:
        thread_template = Template(thread_template_file.read())

        return thread_template.substitute(
            result = '🟢 Aprovadas' if result == 'Aprovado' else '🔴 Rejeitadas',
            date_start = date_start,
            date_end = date_end,
        )

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

def group_votes_by_result(votes: list[dict]) -> dict[str, list[dict]]:
    votes_by_result = {}

    for vote in votes:
        result = vote['result']
        votes_by_result[result] = votes_by_result.get(result, [])
        votes_by_result[result].append(vote)

    return votes_by_result

def update(legislature: str, state_file_path = 'state.json'):
    with StateStorage(file_path = state_file_path) as state:
            print('fetching votes')
            raw_votes = fetch_votes_for_legislature(legislature)

            if MARK_ALL_AS_PUBLISHED:
                print('marking all votes as published')
                state.state = {}
                for raw_vote in raw_votes:
                    state.mark_vote_published(raw_vote['vote_id'])

            new_votes = [parse_vote(raw_vote) for raw_vote in raw_votes if state.is_new_vote(raw_vote['vote_id'])]

            if not new_votes:
                print('no new votes')
                return

            if len(new_votes) > 100 and not OVERRIDE_TOO_MANY_NEW_VOTES_CHECK:
                raise AssertionError(f'Found {len(new_votes)} new votes, state might have been lost, aborting.')

            print('posting votes')
            m = MastodonClient()

            new_votes_by_result = group_votes_by_result(new_votes)

            for result in sorted(new_votes_by_result):
                new_votes_for_result = new_votes_by_result[result]
                print(f'starting a thread for result {result}')
                new_votes_for_result.sort(key = itemgetter('date'))

                idempotency_key = str(hash(vote for vote in new_votes))
                result_thread = m.start_vote_thread(render_thread(result, new_votes_for_result), idempotency_key = idempotency_key)

                for new_vote_for_result in new_votes_for_result:
                    vote_id = new_vote_for_result['vote_id']

                    print(f'posting vote {new_vote_for_result}')
                    m.post_vote(render_vote(new_vote_for_result), reply_to = result_thread, idempotency_key = vote_id)
                    state.mark_vote_published(vote_id)

if __name__ == '__main__':
    load_dotenv()
    update('XVI')
    print('done')

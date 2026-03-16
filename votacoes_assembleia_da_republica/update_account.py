import os
import datetime
import hashlib
from dotenv import load_dotenv
from operator import itemgetter
from string import Template
from mastodon import MastodonError

from votacoes_assembleia_da_republica.state_storage import StateStorage
from votacoes_assembleia_da_republica.mastodon_client import MastodonClient
from votacoes_assembleia_da_republica.fetch_votes import fetch_votes_for_legislature, parse_vote

if __name__ == "__main__":
    load_dotenv()

DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
TOOT_MAX_LENGTH = 500


def render_thread(result: str, sorted_new_votes: list[dict]) -> str:
    date_start = sorted_new_votes[0]["date"]
    date_end = sorted_new_votes[-1]["date"]

    with open("vote_thread.template", "r") as thread_template_file:
        thread_template = Template(thread_template_file.read())

        return thread_template.substitute(result="🟢 Aprovadas" if result == "Aprovado" else "🔴 Rejeitadas", date_start=date_start, date_end=date_end)


def render_vote(vote: dict) -> str:
    with open("vote_status.template", "r") as toot_template_file:
        toot_template = Template(toot_template_file.read())

        vote_detail = vote["vote_detail"]
        if vote_detail == "unanime":
            rendered_vote_detail = "🤝 Unânime"
        elif vote_detail == "prejudicado":
            rendered_vote_detail = "⚪ Prejudicado"
        else:
            with open("vote_detail.template", "r") as vote_detail_template_file:
                vote_detail_template = Template(vote_detail_template_file.read())
                rendered_vote_detail = vote_detail_template.substitute(
                    in_favour=", ".join(vote_detail["in_favour"]),
                    against=", ".join(vote_detail["against"]),
                    abstained=", ".join(vote_detail["abstained"] + vote_detail["absent"]),
                )

        rendered = toot_template.substitute(
            result="🟢 Aprovado" if vote["result"] == "Aprovado" else "🔴 Rejeitado",
            date=vote["date"],
            type=vote["initiative_type"],
            authors=", ".join(vote["authors"]),
            title=vote["title"],
            phase=vote["phase"],
            vote_detail=rendered_vote_detail,
            initiative_uri=vote["initiative_uri"],
        )

        # Mastodon always counts urls as 23 characters
        rendered_length = len(rendered) - len(vote["initiative_uri"]) + 23

        if rendered_length <= TOOT_MAX_LENGTH:
            return rendered

        rest_of_text = rendered_length - len(vote["title"])
        title_max_length = TOOT_MAX_LENGTH - rest_of_text - 3

        return toot_template.substitute(
            result="🟢 Aprovado" if vote["result"] == "Aprovado" else "🔴 Rejeitado",
            date=vote["date"],
            type=vote["initiative_type"],
            authors=", ".join(vote["authors"]),
            title=f"{vote['title'][:title_max_length]}...",
            phase=vote["phase"],
            vote_detail=rendered_vote_detail,
            initiative_uri=vote["initiative_uri"],
        )


def group_votes_by_result(votes: list[dict]) -> dict[str, list[dict]]:
    votes_by_result = {}

    for vote in votes:
        result = vote["result"]
        votes_by_result[result] = votes_by_result.get(result, [])
        votes_by_result[result].append(vote)

    return votes_by_result


def update(legislature: str, state_file_path="state.json", use_github=False):
    OVERRIDE_UNSAFE_STATE_CHECK = os.environ.get("OVERRIDE_UNSAFE_STATE_CHECK", "false").lower() == "true"
    OVERRIDE_TOO_MANY_NEW_VOTES_ALLOW_AFTER_ISO_DATE = os.environ.get("OVERRIDE_TOO_MANY_NEW_VOTES_ALLOW_AFTER_ISO_DATE", datetime.date.today().isoformat())

    with StateStorage(legislature, file_path=state_file_path, use_github=use_github) as state:
        print("fetching votes")
        raw_votes = fetch_votes_for_legislature(legislature)

        new_votes = [parse_vote(raw_vote) for raw_vote in raw_votes if state.is_new_vote(raw_vote["vote_id"])]

        if not new_votes:
            print("no new votes")
            return

        if len(new_votes) > 100 and not OVERRIDE_UNSAFE_STATE_CHECK:
            raise AssertionError(f"Found {len(new_votes)} new votes, state might have been lost, aborting.")

        if OVERRIDE_UNSAFE_STATE_CHECK:
            print(f"Found {len(new_votes)} new votes, overriding check and allowing the ones after: {OVERRIDE_TOO_MANY_NEW_VOTES_ALLOW_AFTER_ISO_DATE}")
            for expired_vote in new_votes:
                if expired_vote["date"] <= OVERRIDE_TOO_MANY_NEW_VOTES_ALLOW_AFTER_ISO_DATE:
                    state.skip_vote(expired_vote["vote_id"])

            new_votes = [vote for vote in new_votes if vote["date"] > OVERRIDE_TOO_MANY_NEW_VOTES_ALLOW_AFTER_ISO_DATE]

        print("posting votes")
        m = MastodonClient()

        stored_last_post_id = state.read_last_post_id()
        if stored_last_post_id is not None and not OVERRIDE_UNSAFE_STATE_CHECK:
            actual_last_post_id = m.latest_post_id()
            if actual_last_post_id != stored_last_post_id:
                raise AssertionError(
                    f"Last post ID mismatch: stored={stored_last_post_id}, actual={actual_last_post_id}. State may be stale, aborting to avoid duplicate posts."
                )

        new_votes_by_result = group_votes_by_result(new_votes)

        last_post_id = None
        for result in sorted(new_votes_by_result):
            new_votes_for_result = new_votes_by_result[result]
            print(f"starting a thread for result {result}")
            new_votes_for_result.sort(key=itemgetter("date"))

            idempotency_key = hashlib.md5(",".join(sorted(v["vote_id"] for v in new_votes_for_result)).encode()).hexdigest()
            result_thread = m.start_vote_thread(render_thread(result, new_votes_for_result), idempotency_key=idempotency_key)

            for new_vote_for_result in new_votes_for_result:
                vote_id = new_vote_for_result["vote_id"]

                print(f"posting vote {new_vote_for_result}")
                try:
                    post = m.post_vote(render_vote(new_vote_for_result), reply_to=result_thread, idempotency_key=vote_id)
                    state.mark_vote_published(vote_id)
                    if post is not None:
                        last_post_id = str(post["id"])
                except MastodonError as e:
                    print(f"error posting vote {vote_id}: {e}")
                    state.mark_vote_errored(vote_id)

        if last_post_id is not None:
            state.set_last_post_id(last_post_id)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--github-state", action="store_true", help="Read/write state from GitHub variable instead of local state.json")
    args = parser.parse_args()
    update("XVII", use_github=args.github_state)
    print("done")

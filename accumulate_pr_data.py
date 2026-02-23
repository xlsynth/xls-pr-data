#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import logging
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

import requests
import csv
import os
import sys
from datetime import datetime
from typing import Dict, Iterable, Optional, Tuple

def parse_bool_field(raw_value):
    if raw_value is None:
        return False
    text = str(raw_value).strip().lower()
    if text in ("1", "true", "t", "yes", "y"):
        return True
    if text in ("", "0", "false", "f", "no", "n", "none", "null"):
        return False
    raise ValueError(f"Unexpected boolean value: {raw_value!r}")


def parse_optional_bool_field(raw_value):
    if raw_value is None:
        return None
    text = str(raw_value).strip().lower()
    if text in ("1", "true", "t", "yes", "y"):
        return True
    if text in ("0", "false", "f", "no", "n"):
        return False
    if text in ("", "none", "null"):
        return None
    raise ValueError(f"Unexpected optional boolean value: {raw_value!r}")


def fetch_prs(max_pages=None):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        logging.error("Please set GITHUB_TOKEN environment variable.")
        sys.exit(1)

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    url = "https://api.github.com/repos/google/xls/pulls?state=all&per_page=100"
    prs = []
    page = 1
    while True:
        logging.info(f"Fetching page {page} of PRs...")
        response = requests.get(url + f"&page={page}", headers=headers)
        response.raise_for_status()
        data = response.json()
        if not data:
            break
        prs.extend(data)
        if max_pages is not None and page >= max_pages:
            break
        page += 1
    logging.info(f"Fetched {len(prs)} PRs in total.")
    return prs


def fetch_timeline_events(pr_number):
    token = os.environ.get("GITHUB_TOKEN")
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.mockingbird-preview+json",
    }
    url = f"https://api.github.com/repos/google/xls/issues/{pr_number}/timeline?per_page=100"
    events = []
    page = 1
    while True:
        response = requests.get(url + f"&page={page}", headers=headers)
        response.raise_for_status()
        data = response.json()
        if not data:
            break
        events.extend(data)
        page += 1
    return events


def fetch_paginated_json(url, headers):
    items = []
    page = 1
    while True:
        response = requests.get(url + f"&page={page}", headers=headers)
        response.raise_for_status()
        data = response.json()
        if not data:
            break
        items.extend(data)
        page += 1
    return items


def fetch_supplemental_turn_events(pr_number):
    token = os.environ.get("GITHUB_TOKEN")
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    base = "https://api.github.com/repos/google/xls"
    events = []

    reviews_url = f"{base}/pulls/{pr_number}/reviews?per_page=100"
    for review in fetch_paginated_json(reviews_url, headers):
        submitted_at = review.get("submitted_at")
        if not submitted_at:
            continue
        events.append(
            {
                "event": "review_submitted",
                "created_at": submitted_at,
                "user": review.get("user"),
                "state": review.get("state"),
            }
        )

    review_comments_url = f"{base}/pulls/{pr_number}/comments?per_page=100"
    for comment in fetch_paginated_json(review_comments_url, headers):
        created_at = comment.get("created_at")
        if not created_at:
            continue
        events.append(
            {
                "event": "pull_request_review_comment",
                "created_at": created_at,
                "user": comment.get("user"),
            }
        )

    issue_comments_url = f"{base}/issues/{pr_number}/comments?per_page=100"
    for comment in fetch_paginated_json(issue_comments_url, headers):
        created_at = comment.get("created_at")
        if not created_at:
            continue
        events.append(
            {
                "event": "commented",
                "created_at": created_at,
                "user": comment.get("user"),
            }
        )

    commits_url = f"{base}/pulls/{pr_number}/commits?per_page=100"
    for commit in fetch_paginated_json(commits_url, headers):
        commit_info = commit.get("commit") or {}
        committer_info = commit_info.get("committer") or {}
        created_at = committer_info.get("date")
        if not created_at:
            continue
        actor = commit.get("author") or commit.get("committer")
        events.append(
            {
                "event": "committed",
                "created_at": created_at,
                "actor": actor,
                "user": actor,
            }
        )

    return events


def fetch_all_events(pr_number):
    timeline_events = fetch_timeline_events(pr_number)
    supplemental_events = fetch_supplemental_turn_events(pr_number)

    existing_keys = {
        (event.get("event"), event.get("created_at"))
        for event in timeline_events
        if event.get("created_at")
    }
    merged = list(timeline_events)
    for event in supplemental_events:
        key = (event.get("event"), event.get("created_at"))
        if key in existing_keys:
            continue
        merged.append(event)
        existing_keys.add(key)

    indexed = list(enumerate(merged))
    indexed.sort(
        key=lambda pair: (
            parse_event_time(pair[1]) is None,
            parse_event_time(pair[1]) or datetime.max,
            pair[0],
        )
    )
    return [event for _, event in indexed]


def is_xlsynth_org_member(login: str, membership_cache: Dict[str, Optional[bool]]) -> Optional[bool]:
    if not login:
        return False
    if login in membership_cache:
        return membership_cache[login]

    token = os.environ.get("GITHUB_TOKEN")
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    url = f"https://api.github.com/orgs/xlsynth/members/{login}"
    response = requests.get(url, headers=headers)
    if response.status_code == 204:
        membership_cache[login] = True
        return True
    if response.status_code == 404:
        membership_cache[login] = False
        return False
    if response.status_code == 403:
        # xlsynth org may forbid classic PAT membership checks.
        membership_cache[login] = None
        return None
    logging.warning(
        "Could not determine xlsynth org membership for '%s' (status=%s).",
        login,
        response.status_code,
    )
    membership_cache[login] = None
    return None


def classify_google_side_actor(
    login: str,
    membership_cache: Dict[str, Optional[bool]],
    pr_author_login: str,
) -> bool:
    # Treat PR author as xlsynth side; this keeps author updates on xlsynth-origin
    # PRs from being misclassified when org membership APIs are unavailable.
    if pr_author_login and login == pr_author_login:
        return False
    # Policy: anybody not in xlsynth org is considered Google-side.
    membership = is_xlsynth_org_member(login, membership_cache)
    return membership is not True


def is_author_commit_event(event: dict, pr_author_login: str) -> bool:
    if event.get("event") != "committed":
        return False
    for key in ("actor", "author", "committer", "user"):
        login = (event.get(key) or {}).get("login")
        if login and login == pr_author_login:
            return True
    return False


def extract_actor_login(event: dict) -> Optional[str]:
    for key in ("actor", "user", "author", "committer"):
        login = (event.get(key) or {}).get("login")
        if login:
            return login
    return None


def parse_event_time(event: dict) -> Optional[datetime]:
    created_at = event.get("created_at")
    if not created_at:
        return None
    try:
        return datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def event_is_feedback(event_name: str) -> bool:
    return event_name in {
        "review_submitted",
        "reviewed",
        "commented",
        "pull_request_review_comment",
    }


def event_is_approval_review(event: dict) -> bool:
    event_name = event.get("event", "")
    if event_name not in {"review_submitted", "reviewed"}:
        return False
    state = (event.get("state") or "").lower()
    return state == "approved"


def event_is_resolution(event_name: str) -> bool:
    return event_name in {
        "resolved",
        "review_thread_resolved",
    }


def event_is_author_response(event_name: str) -> bool:
    return event_name in {
        "commented",
        "review_submitted",
        "reviewed",
        "pull_request_review_comment",
    }


def event_is_relevant_for_turn(event_name: str) -> bool:
    return event_name in {
        "review_submitted",
        "reviewed",
        "commented",
        "pull_request_review_comment",
        "committed",
        "review_requested",
        "review_request_removed",
        "ready_for_review",
        "converted_to_draft",
        "labeled",
        "unlabeled",
        "head_ref_force_pushed",
    }


def get_turn_state(
    events: Iterable[dict],
    pr_author_login: str,
    membership_cache: Dict[str, Optional[bool]],
) -> Tuple[Optional[bool], Optional[str], Optional[str]]:
    unresolved_googler_feedback = []
    last_relevant_actor = None
    last_relevant_at = None
    last_relevant_was_approval = False

    for event in events:
        event_name = event.get("event", "")
        event_time = event.get("created_at")
        event_dt = parse_event_time(event)
        actor_login = extract_actor_login(event)
        event_is_approval = event_is_approval_review(event)

        if event_is_relevant_for_turn(event_name) and actor_login and event_time:
            last_relevant_actor = actor_login
            last_relevant_at = event_time
            last_relevant_was_approval = event_is_approval

        if event_is_feedback(event_name) and actor_login and event_dt:
            if event_is_approval:
                # Approval should not block turn ownership and supersedes earlier
                # feedback under the current heuristic.
                unresolved_googler_feedback = []
                continue
            is_google = classify_google_side_actor(
                login=actor_login,
                membership_cache=membership_cache,
                pr_author_login=pr_author_login,
            )
            if is_google:
                unresolved_googler_feedback.append(event_dt)
                continue

        if event_is_resolution(event_name):
            if unresolved_googler_feedback:
                unresolved_googler_feedback.pop()
            continue

        if event_dt and pr_author_login and is_author_commit_event(event, pr_author_login):
            unresolved_googler_feedback = [
                feedback_dt
                for feedback_dt in unresolved_googler_feedback
                if feedback_dt > event_dt
            ]
            continue

        if (
            event_dt
            and actor_login
            and pr_author_login
            and actor_login == pr_author_login
            and event_is_author_response(event_name)
        ):
            # Pragmatic heuristic: author replies after Googler feedback can count
            # as "addressed" even without explicit thread resolution.
            unresolved_googler_feedback = [
                feedback_dt
                for feedback_dt in unresolved_googler_feedback
                if feedback_dt > event_dt
            ]

    if unresolved_googler_feedback:
        return False, last_relevant_actor, last_relevant_at

    if not last_relevant_actor:
        return None, None, None

    if last_relevant_was_approval:
        return True, last_relevant_actor, last_relevant_at

    actor_is_google = classify_google_side_actor(
        login=last_relevant_actor,
        membership_cache=membership_cache,
        pr_author_login=pr_author_login,
    )
    return (not actor_is_google), last_relevant_actor, last_relevant_at


def process_pr(pr, membership_cache=None):
    if membership_cache is None:
        membership_cache = {}

    pr_number = pr["number"]
    created_at = pr["created_at"]
    pr_updated_at = pr.get("updated_at")
    is_draft = bool(pr.get("draft", False))
    review_requested_at = None
    reviewing_internally_at = None
    closed_at = None
    ready_for_review_at = None
    first_review_at = None

    events = fetch_all_events(pr_number)
    for event in events:
        if event.get("event") == "closed" and closed_at is None:
            closed_at = event.get("created_at")
            break  # Only use events from the first lifecycle
        if event.get("event") == "review_requested" and review_requested_at is None:
            review_requested_at = event.get("created_at")
        if event.get("event") == "ready_for_review" and ready_for_review_at is None:
            ready_for_review_at = event.get("created_at")
        if event.get("event") in ["review_submitted", "reviewed"] and first_review_at is None:
            first_review_at = event.get("created_at")
        if event.get("event") == "labeled":
            label = event.get("label", {}).get("name", "").lower()
            if label == "reviewing internally" and reviewing_internally_at is None:
                reviewing_internally_at = event.get("created_at")

    # Fallback: if no explicit review requested event and PR is not a draft, then:
    if not review_requested_at and not pr.get("draft", False):
        if ready_for_review_at:
            review_requested_at = ready_for_review_at
        elif first_review_at:
            review_requested_at = first_review_at
        else:
            review_requested_at = created_at

    head = pr.get("head") or {}
    repo = head.get("repo") or {}
    head_repo = repo.get("full_name", "")
    pr_author_login = (pr.get("user") or {}).get("login", "")
    is_googles_turn = None
    last_relevant_actor = None
    last_relevant_at = None

    # Determine the final 'closed_at' value and aggressively sanitize it.
    raw_closed_at = closed_at or pr.get("closed_at")
    final_closed_at = sanitize_field(raw_closed_at) if raw_closed_at else raw_closed_at

    if not is_draft and not final_closed_at:
        is_googles_turn, last_relevant_actor, last_relevant_at = get_turn_state(
            events=events,
            pr_author_login=pr_author_login,
            membership_cache=membership_cache,
        )

    # Assert that the 'closed_at' value contains no carriage returns or newlines.
    if final_closed_at:
        assert "\r" not in final_closed_at and "\n" not in final_closed_at, \
            f"closed_at field contains forbidden characters: {final_closed_at}"

    return {
        "pr_number": pr_number,
        "head_repo": head_repo,
        "created_at": created_at,
        "pr_updated_at": pr_updated_at,
        "is_draft": is_draft,
        "review_requested_at": review_requested_at,
        "reviewing_internally_at": reviewing_internally_at,
        "closed_at": final_closed_at,
        "last_relevant_actor": last_relevant_actor,
        "last_relevant_at": last_relevant_at,
        "is_googles_turn": is_googles_turn,
    }


def get_pr_landing_latency(record):
    """Compute latency in hours from review requested to closed (or current time if open) for a given PR record. Returns a float or None."""
    if record.get("is_draft"):
        return None
    if not record.get("review_requested_at"):
        return None
    dt_format = '%Y-%m-%dT%H:%M:%SZ'
    try:
        review_time = datetime.strptime(record["review_requested_at"], dt_format)
        # If PR is closed, use the closed_at timestamp; otherwise, use the current UTC time.
        closed_str = record.get("closed_at")
        if closed_str:
            closed_time = datetime.strptime(closed_str, dt_format)
        else:
            closed_time = datetime.utcnow()
        return (closed_time - review_time).total_seconds() / 3600
    except Exception as e:
        logging.warning(f"Failed to compute latency for PR #{record.get('pr_number')}: {e}")
    return None


def sanitize_field(field):
    # Remove all carriage return and newline characters, and trim surrounding whitespace.
    return field.replace('\r', '').replace('\n', '').strip() if field else field


def sanitize_record(record):
    # Sanitize all string fields in the record.
    return {key: sanitize_field(val) if isinstance(val, str) else val
            for key, val in record.items()}


def main():
    parser = argparse.ArgumentParser(description="Accumulate GitHub PR data.")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit the number of PR pages to fetch for testing.")
    args = parser.parse_args()

    csv_file = "pr_data.csv"
    all_records = {}
    try:
        with open(csv_file, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Sanitize the 'closed_at' field (or ideally all fields) as soon as we read them.
                row["closed_at"] = sanitize_field(row.get("closed_at"))
                row["is_draft"] = parse_bool_field(row.get("is_draft"))
                row["is_googles_turn"] = parse_optional_bool_field(row.get("is_googles_turn"))
                all_records[str(row["pr_number"])] = row
        logging.info(f"Loaded {len(all_records)} existing PR records from CSV.")
    except FileNotFoundError:
        logging.info("CSV file not found. A new one will be created.")

    prs = fetch_prs(args.max_pages)
    membership_cache: Dict[str, Optional[bool]] = {}
    updated_records = {}
    total = len(prs)
    for idx, pr in enumerate(prs, start=1):
        remaining = total - idx
        pr_number = str(pr["number"])
        # If record exists and the PR is not open, keep existing record.
        if pr_number in all_records:
            existing_record = all_records[pr_number]
            if existing_record.get("closed_at"):
                logging.info(
                    f"Skipping PR #{pr_number} as it's already marked as closed in CSV. {remaining} PR(s) remaining."
                )
                updated_records[pr_number] = sanitize_record(existing_record)
                continue
            else:
                existing_updated_at = sanitize_field(existing_record.get("pr_updated_at"))
                latest_updated_at = sanitize_field(pr.get("updated_at"))
                if existing_updated_at and latest_updated_at and existing_updated_at == latest_updated_at:
                    logging.info(
                        f"PR #{pr_number} unchanged since last scrape. Reusing cached row. {remaining} PR(s) remaining."
                    )
                    updated_records[pr_number] = sanitize_record(existing_record)
                    continue
                logging.info(
                    f"PR #{pr_number} changed or missing update timestamp. Reprocessing. {remaining} PR(s) remaining."
                )
        else:
            logging.info(f"Processing new PR #{pr_number}... {remaining} PR(s) remaining.")
        record = process_pr(
            pr,
            membership_cache=membership_cache,
        )
        updated_records[pr_number] = record
        latency = get_pr_landing_latency(record)
        if latency is not None:
            logging.info(f"PR #{pr_number} latency from review requested to closed: {latency:.2f} hours")

    # Before writing, sanitize every record as a last pass.
    sanitized_records = [sanitize_record(rec) for rec in updated_records.values()]
    # Write all updated records to CSV (rewrite entire file) using newline=""
    with open(csv_file, "w", newline="") as csvfile:
        fieldnames = [
            "pr_number",
            "head_repo",
            "created_at",
            "pr_updated_at",
            "is_draft",
            "review_requested_at",
            "reviewing_internally_at",
            "closed_at",
            "last_relevant_actor",
            "last_relevant_at",
            "is_googles_turn",
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sanitized_records)
    logging.info(f"Updated CSV file '{csv_file}' with {len(sanitized_records)} PR records.")


if __name__ == "__main__":
    main()

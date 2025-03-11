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


def process_pr(pr):
    pr_number = pr["number"]
    created_at = pr["created_at"]
    review_requested_at = None
    reviewing_internally_at = None
    closed_at = None

    events = fetch_timeline_events(pr_number)
    for event in events:
        if event.get("event") == "closed" and closed_at is None:
            closed_at = event.get("created_at")
            break  # Only use events from the first lifecycle
        if event.get("event") == "review_requested" and review_requested_at is None:
            review_requested_at = event.get("created_at")
        if event.get("event") == "labeled":
            label = event.get("label", {}).get("name", "").lower()
            if label == "reviewing internally" and reviewing_internally_at is None:
                reviewing_internally_at = event.get("created_at")

    head = pr.get("head") or {}
    repo = head.get("repo") or {}
    head_repo = repo.get("full_name", "")

    # Determine the final 'closed_at' value and aggressively sanitize it.
    raw_closed_at = closed_at or pr.get("closed_at")
    final_closed_at = sanitize_field(raw_closed_at) if raw_closed_at else raw_closed_at

    # Assert that the 'closed_at' value contains no carriage returns or newlines.
    if final_closed_at:
        assert "\r" not in final_closed_at and "\n" not in final_closed_at, \
            f"closed_at field contains forbidden characters: {final_closed_at}"

    return {
        "pr_number": pr_number,
        "head_repo": head_repo,
        "created_at": created_at,
        "review_requested_at": review_requested_at,
        "reviewing_internally_at": reviewing_internally_at,
        "closed_at": final_closed_at
    }


def get_pr_landing_latency(record):
    """Compute latency in hours from review requested to closed (or current time if open) for a given PR record. Returns a float or None."""
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
            closed_time = datetime.now(datetime.UTC)
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
                all_records[str(row["pr_number"])] = row
        logging.info(f"Loaded {len(all_records)} existing PR records from CSV.")
    except FileNotFoundError:
        logging.info("CSV file not found. A new one will be created.")

    prs = fetch_prs(args.max_pages)
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
                logging.info(
                    f"PR #{pr_number} is not yet marked as closed in CSV. Reprocessing for updates. {remaining} PR(s) remaining."
                )
        else:
            logging.info(f"Processing new PR #{pr_number}... {remaining} PR(s) remaining.")
        record = process_pr(pr)
        updated_records[pr_number] = record
        latency = get_pr_landing_latency(record)
        if latency is not None:
            logging.info(f"PR #{pr_number} latency from review requested to closed: {latency:.2f} hours")

    # Before writing, sanitize every record as a last pass.
    sanitized_records = [sanitize_record(rec) for rec in updated_records.values()]
    # Write all updated records to CSV (rewrite entire file) using newline=""
    with open(csv_file, "w", newline="") as csvfile:
        fieldnames = ["pr_number", "head_repo", "created_at", "review_requested_at", "reviewing_internally_at", "closed_at"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(sanitized_records)
    logging.info(f"Updated CSV file '{csv_file}' with {len(sanitized_records)} PR records.")


if __name__ == "__main__":
    main()

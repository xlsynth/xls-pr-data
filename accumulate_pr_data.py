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
    return {
        "pr_number": pr_number,
        "head_repo": head_repo,
        "created_at": created_at,
        "review_requested_at": review_requested_at,
        "reviewing_internally_at": reviewing_internally_at,
        "closed_at": closed_at or pr.get("closed_at")
    }


def get_pr_landing_latency(record):
    """Compute latency in hours from review requested to closed for a given PR record. Returns a float or None."""
    if record.get("review_requested_at") and record.get("closed_at"):
        try:
            dt_format = '%Y-%m-%dT%H:%M:%SZ'
            review_time = datetime.strptime(record["review_requested_at"], dt_format)
            closed_time = datetime.strptime(record["closed_at"], dt_format)
            return (closed_time - review_time).total_seconds() / 3600
        except Exception as e:
            logging.warning(f"Failed to compute latency for PR #{record.get('pr_number')}: {e}")
    return None


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
                all_records[str(row["pr_number"])] = row
        logging.info(f"Loaded {len(all_records)} existing PR records from CSV.")
    except FileNotFoundError:
        logging.info("CSV file not found. A new one will be created.")

    prs = fetch_prs(args.max_pages)
    updated_records = {}
    for pr in prs:
        pr_number = str(pr["number"])
        # If record exists and the PR is not open, keep existing record.
        if pr_number in all_records:
            if pr.get("state", "").lower() != "open":
                logging.info(f"Skipping PR #{pr_number} as it's already processed and closed.")
                updated_records[pr_number] = all_records[pr_number]
                continue
            else:
                logging.info(f"PR #{pr_number} is still open. Reprocessing for updates.")
        else:
            logging.info(f"Processing new PR #{pr_number}...")
        record = process_pr(pr)
        updated_records[pr_number] = record
        latency = get_pr_landing_latency(record)
        if latency is not None:
            logging.info(f"PR #{pr_number} latency from review requested to closed: {latency:.2f} hours")

    # Write all updated records to CSV (rewrite entire file)
    with open(csv_file, "w", newline="") as csvfile:
        fieldnames = ["pr_number", "head_repo", "created_at", "review_requested_at", "reviewing_internally_at", "closed_at"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated_records.values())
    logging.info(f"Updated CSV file '{csv_file}' with {len(updated_records)} PR records.")


if __name__ == "__main__":
    main()

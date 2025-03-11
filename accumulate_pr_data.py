#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

import requests
import csv
import os
import sys
from datetime import datetime


def fetch_prs():
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

    head_repo = pr.get("head", {}).get("repo", {}).get("full_name", "")
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
    csv_file = "pr_data.csv"
    existing_data = {}
    try:
        with open(csv_file, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_data[str(row["pr_number"])] = row
        logging.info(f"Loaded {len(existing_data)} existing PR records from CSV.")
    except FileNotFoundError:
        logging.info("CSV file not found. A new one will be created.")

    prs = fetch_prs()
    new_records = []
    for pr in prs:
        pr_number = str(pr["number"])
        if pr_number in existing_data:
            logging.info(f"Skipping PR #{pr_number} as it's already processed.")
            continue
        logging.info(f"Processing PR #{pr_number}...")
        record = process_pr(pr)
        new_records.append(record)
        latency = get_pr_landing_latency(record)
        if latency is not None:
            logging.info(f"PR #{pr_number} latency from review requested to closed: {latency:.2f} hours")

    if not new_records:
        logging.info("No new PRs to add.")
        return

    write_header = not existing_data
    with open(csv_file, "a", newline="") as csvfile:
        fieldnames = ["pr_number", "head_repo", "created_at", "review_requested_at", "reviewing_internally_at", "closed_at"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerows(new_records)
    logging.info(f"Updated CSV file '{csv_file}' with {len(new_records)} new PR records.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import requests
import csv
import os
import sys
from datetime import datetime


def fetch_prs():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Please set GITHUB_TOKEN environment variable.")
        sys.exit(1)
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    url = "https://api.github.com/repos/google/xls/pulls?state=all&per_page=100"
    prs = []
    page = 1
    while True:
        response = requests.get(url + f"&page={page}", headers=headers)
        response.raise_for_status()
        data = response.json()
        if not data:
            break
        prs.extend(data)
        page += 1
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
    closed_at = pr.get("closed_at")  # might be None if still open

    events = fetch_timeline_events(pr_number)
    review_requested_at = None
    reviewing_internally_at = None

    for event in events:
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
        "closed_at": closed_at,
    }


def main():
    prs = fetch_prs()
    processed = []
    for pr in prs:
        processed.append(process_pr(pr))
    
    with open("pr_data.csv", "w", newline="") as csvfile:
        fieldnames = ["pr_number", "head_repo", "created_at", "review_requested_at", "reviewing_internally_at", "closed_at"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(processed)
    print("CSV file 'pr_data.csv' has been created with PR data.")


if __name__ == "__main__":
    main() 
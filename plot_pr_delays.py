#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

import pandas as pd
import matplotlib.pyplot as plt
import os
import json
from datetime import time, datetime
import pytz

# Global constants for allowed thresholds
BUSINESS_START = time(9, 0)          # Business start when review can begin
BUSINESS_END = time(17, 0)           # Business end
ALLOWED_MAX = time(12, 0)            # Latest allowed effective review time (inclusive)

def is_business_hours(timestamp):
    """Check if a timestamp falls within business hours (9 AM - 5 PM PT, Monday-Friday)."""
    pt = pytz.timezone('America/Los_Angeles')
    dt = timestamp.astimezone(pt)
    business_start = BUSINESS_START
    business_end = BUSINESS_END

    if dt.weekday() >= 5:
        return False
    return business_start <= dt.time() <= business_end

def adjust_review_time(timestamp):
    """Return the effective review time in PT based on our policy."""
    pt = pytz.timezone('America/Los_Angeles')
    return effective_review_time(timestamp).astimezone(pt)

def bump_to_next_business_day(dt):
    """Return the next business day at 9 AM given a datetime in PT."""
    pt = pytz.timezone('America/Los_Angeles')
    next_day = dt + pd.Timedelta(days=1)
    while next_day.weekday() >= 5:  # Saturday=5, Sunday=6
        next_day += pd.Timedelta(days=1)
    return next_day.replace(hour=BUSINESS_START.hour, minute=BUSINESS_START.minute, second=0, microsecond=0)

def effective_review_time(timestamp):
    """Return the effective review request time in UTC based on policy (PT):

    For any day:
      - If before BUSINESS_START (9:00 AM) or after ALLOWED_MAX (12:00 PM),
        effective time = next business day at BUSINESS_START.
      - Otherwise, no adjustment.
    Returns time in UTC.
    """
    pt = pytz.timezone('America/Los_Angeles')
    dt_pt = timestamp.astimezone(pt)

    if dt_pt.time() < BUSINESS_START or dt_pt.time() > ALLOWED_MAX:
        effective_dt = bump_to_next_business_day(dt_pt)
    else:
        effective_dt = dt_pt

    return effective_dt.astimezone(pytz.utc)

def calculate_latency(review_time, close_time):
    """Calculate latency in hours between review request and close time using effective review time."""
    if pd.isna(review_time) or pd.isna(close_time):
        return None
    effective_time = effective_review_time(review_time)
    latency = (close_time - effective_time).total_seconds() / 3600
    return max(0, latency)  # Ensure non-negative latency

def main():
    # Read CSV data
    df = pd.read_csv('pr_data.csv')
    metadata_file = "pr_data_meta.json"
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, "r") as f:
                metadata = json.load(f)
            data_collected = pd.to_datetime(metadata.get("last_scrape"))
        except Exception:
            data_collected = pd.Timestamp.now(tz='UTC')
    else:
        data_collected = pd.Timestamp.now(tz='UTC')
    data_time_str = data_collected.strftime('%Y-%m-%d %H:%M:%S')

    # Filter for PRs from xlsynth/xlsynth
    df = df[df['head_repo'] == 'xlsynth/xlsynth']

    # Exclude draft PRs from latency reporting/plotting.
    if 'is_draft' not in df.columns:
        df['is_draft'] = False
    else:
        def _parse_is_draft(value):
            if pd.isna(value):
                return False
            text = str(value).strip().lower()
            if text in ("1", "true", "t", "yes", "y"):
                return True
            if text in ("", "0", "false", "f", "no", "n", "none", "null"):
                return False
            raise ValueError(f"Unexpected is_draft value: {value!r}")

        df['is_draft'] = df['is_draft'].apply(_parse_is_draft)
    df = df[~df['is_draft']]

    # Parse dates
    for col in ['created_at', 'review_requested_at', 'reviewing_internally_at', 'closed_at']:
        df[col] = pd.to_datetime(df[col], errors='coerce')

    # Get current UTC time
    current_utc = pd.Timestamp.now(tz='UTC')

    # Identify open PRs (those with missing 'closed_at')
    open_prs = df[df['closed_at'].isna()]
    open_pr_count = len(open_prs)
    pt = pytz.timezone('America/Los_Angeles')
    if open_pr_count > 0:
        print("\nOpen PRs and their current latency:")
        print("-" * 80)
        for idx, row in open_prs.iterrows():
            latency = calculate_latency(row['review_requested_at'], current_utc)
            latency_str = f"{latency:.2f} hours" if latency is not None else "N/A"

            # Calculate raw latency for comparison
            if not pd.isna(row['review_requested_at']):
                raw_latency = (current_utc - row['review_requested_at']).total_seconds() / 3600
                adjusted_time = adjust_review_time(row['review_requested_at'])
                time_diff = (adjusted_time - row['review_requested_at']).total_seconds() / 3600

                if time_diff > 1:  # Only show if adjustment made more than 1 hour difference
                    original_pt = row['review_requested_at'].astimezone(pt)
                    adjusted_pt = adjusted_time.astimezone(pt)

                    print(f"PR #{row['pr_number']}:")
                    print(f"  Review requested: {original_pt.strftime('%A, %Y-%m-%d %H:%M:%S %Z')}")
                    print(f"  Business hours start: {adjusted_pt.strftime('%A, %Y-%m-%d %H:%M:%S %Z')}")
                    print(f"  Unadjusted latency: {raw_latency:.2f} hours")
                    print(f"  Business-hours adjusted latency: {latency:.2f} hours")
                    print(f"  Time adjustment: {time_diff:.2f} hours")
                    print("-" * 80)
                else:
                    print(f"PR #{row['pr_number']}: {latency_str}")
            else:
                print(f"PR #{row['pr_number']}: {latency_str}")
    else:
        print("No open PRs found.")

    # Fill missing 'closed_at' with current UTC for open PRs
    df['closed_at'] = df['closed_at'].fillna(current_utc)

    # Compute latency using the new calculation function
    df['latency'] = df.apply(lambda row: calculate_latency(row['review_requested_at'], row['closed_at']), axis=1)

    # Filter out None latencies
    df = df[df['latency'].notna()]

    # Print closed PRs with significant business hours adjustments
    print("\nClosed PRs with significant business hours adjustments:")
    print("-" * 80)
    for idx, row in df.iterrows():
        if not pd.isna(row['review_requested_at']):
            adjusted_time = adjust_review_time(row['review_requested_at'])
            time_diff = (adjusted_time - row['review_requested_at']).total_seconds() / 3600

            if time_diff > 1:  # Only show if adjustment made more than 1 hour difference
                raw_latency = (row['closed_at'] - row['review_requested_at']).total_seconds() / 3600
                original_pt = row['review_requested_at'].astimezone(pt)
                adjusted_pt = adjusted_time.astimezone(pt)

                print(f"PR #{row['pr_number']}:")
                print(f"  Review requested: {original_pt.strftime('%A, %Y-%m-%d %H:%M:%S %Z')}")
                print(f"  Business hours start: {adjusted_pt.strftime('%A, %Y-%m-%d %H:%M:%S %Z')}")
                print(f"  Unadjusted latency: {raw_latency:.2f} hours")
                print(f"  Business-hours adjusted latency: {row['latency']:.2f} hours")
                print(f"  Time adjustment: {time_diff:.2f} hours")
                print("-" * 80)

    # Assign group based on closed_at date
    now = pd.Timestamp.now(tz='UTC')
    def assign_group(closed_date):
        if closed_date.year == now.year and closed_date.month == now.month:
            return "This Month"
        previous = now - pd.DateOffset(months=1)
        if closed_date.year == previous.year and closed_date.month == previous.month:
            return "Previous Month"
        return "All Before"
    df['group'] = df['closed_at'].apply(assign_group)

    # Define the group order and data for plotting
    groups = ["This Month", "Previous Month", "All Before"]
    data_to_plot = [df[df['group'] == g]['latency'].dropna() for g in groups]
    # Define new x-axis labels with month-year for 'This Month' and 'Previous Month'
    this_month_label_plot = f"This Month\n{now.strftime('%Y-%m')}"
    previous_month_label_plot = f"Previous Month\n{(now - pd.DateOffset(months=1)).strftime('%Y-%m')}"
    all_before_label_plot = "All Before"
    plot_labels = [this_month_label_plot, previous_month_label_plot, all_before_label_plot]

    # Create figure for the plot
    plt.figure(figsize=(10, 6))

    bp = plt.boxplot(data_to_plot, labels=plot_labels, patch_artist=True)

    # Compute summary statistics for 'This Month'
    this_month_data = df[df['group'] == "This Month"]['latency']
    if not this_month_data.empty:
        count = this_month_data.count()
        mean_val = this_month_data.mean()
        median_val = this_month_data.median()
        title = (f"Latency Distribution (n={count}, open={open_pr_count}, avg={mean_val:.2f} hrs, med={median_val:.2f} hrs)\n"
                 f"Data as of: {data_time_str} UTC")
    else:
        title = f"Latency Distribution (No data, open={open_pr_count})\nData as of: {data_time_str} UTC"

    # Define colors for each group
    colors = ['lightgreen', 'skyblue', 'salmon']
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
    plt.ylabel("Latency (Hours)")
    plt.title(title)
    plt.savefig("pr_delays.png")
    print("Plot saved as pr_delays.png")

if __name__ == '__main__':
    main()

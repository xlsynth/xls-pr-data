#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

import pandas as pd
import matplotlib.pyplot as plt

def main():
    # Read CSV data
    df = pd.read_csv('pr_data.csv')
    # Filter for PRs from xlsynth/xlsynth
    df = df[df['head_repo'] == 'xlsynth/xlsynth']

    # Parse dates
    for col in ['created_at', 'review_requested_at', 'reviewing_internally_at', 'closed_at']:
        df[col] = pd.to_datetime(df[col], errors='coerce')

    # Get current UTC time
    current_utc = pd.Timestamp.now(tz='UTC')

    # Identify open PRs (those with missing 'closed_at')
    open_prs = df[df['closed_at'].isna()]
    open_pr_count = len(open_prs)
    if open_pr_count > 0:
        print("Open PRs and their current latency:")
        for idx, row in open_prs.iterrows():
            # If review_requested_at is missing, we cannot compute latency.
            if pd.isna(row['review_requested_at']):
                latency_str = "N/A"
            else:
                latency_val = (current_utc - row['review_requested_at']).total_seconds() / 3600
                latency_str = f"{latency_val:.2f} hours"
            print(f"PR #{row['pr_number']}: {latency_str}")
    else:
        print("No open PRs found.")

    # Fill missing 'closed_at' with current UTC for open PRs
    df['closed_at'] = df['closed_at'].fillna(current_utc)

    # Compute latency from review requested to closed (in hours)
    df['latency'] = (df['closed_at'] - df['review_requested_at']).dt.total_seconds() / 3600

    # Filter out negative latencies
    df = df[df['latency'] >= 0]

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

    # Define the group order
    groups = ["This Month", "Previous Month", "All Before"]
    data_to_plot = [df[df['group'] == g]['latency'].dropna() for g in groups]

    # Compute summary statistics for 'This Month'
    this_month_data = df[df['group'] == "This Month"]['latency']
    if not this_month_data.empty:
        count = this_month_data.count()
        mean_val = this_month_data.mean()
        median_val = this_month_data.median()
        title = (f"Latency Distribution (This Month: n={count}, open={open_pr_count}, "
                 f"avg={mean_val:.2f} hrs, med={median_val:.2f} hrs)")
    else:
        title = f"Latency Distribution (This Month: No data, open={open_pr_count})"

    plt.figure(figsize=(10, 6))
    bp = plt.boxplot(data_to_plot, labels=groups, patch_artist=True)
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

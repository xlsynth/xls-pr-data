#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

import pandas as pd
import matplotlib.pyplot as plt


def main():
    # Read CSV data
    df = pd.read_csv('pr_data.csv')
    # Filter for PRs from xlsynth/xlsynth
    df = df[df['head_repo'] == 'xlsynth/xlsynth']

    # Parse dates and compute delays in hours
    for col in ['created_at', 'review_requested_at', 'reviewing_internally_at', 'closed_at']:
        df[col] = pd.to_datetime(df[col], errors='coerce')

    df['delay_created_to_review_requested'] = (df['review_requested_at'] - df['created_at']).dt.total_seconds() / 3600
    df['delay_review_requested_to_reviewing_internally'] = (df['reviewing_internally_at'] - df['review_requested_at']).dt.total_seconds() / 3600
    df['delay_reviewing_internally_to_closed'] = (df['closed_at'] - df['reviewing_internally_at']).dt.total_seconds() / 3600

    # Prepare data for boxplot; filter out NaN values
    data_to_plot = [
        df['delay_created_to_review_requested'].dropna(),
        df['delay_review_requested_to_reviewing_internally'].dropna(),
        df['delay_reviewing_internally_to_closed'].dropna()
    ]

    labels = [
        'Creation -> Review Requested',
        'Review Requested -> Reviewing Internally',
        'Reviewing Internally -> Closed'
    ]

    plt.figure(figsize=(10, 6))
    plt.boxplot(data_to_plot, labels=labels)
    plt.ylabel('Delay (Hours)')
    plt.title('PR Lifecycle Delays for xlsynth/xlsynth')
    plt.savefig('pr_delays.png')
    print("Plot saved as pr_delays.png")


if __name__ == '__main__':
    main()

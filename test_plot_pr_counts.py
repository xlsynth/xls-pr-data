# SPDX-License-Identifier: Apache-2.0
"""Unit tests for plot_pr_counts.py utility functions."""

import pandas as pd
from plot_pr_counts import count_prs_by_month


def test_count_prs_by_month():
    data = {
        "created_at": [
            "2023-01-15T12:00:00Z",
            "2023-01-20T08:00:00Z",
            "2023-02-01T10:30:00Z",
            "2023-02-10T22:15:00Z",
            "2023-02-28T05:45:00Z",
        ]
    }
    df = pd.DataFrame(data)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)

    counts = count_prs_by_month(df)

    # Expected: 2 PRs in 2023-01 and 3 PRs in 2023-02
    assert counts.loc["2023-01"] == 2
    assert counts.loc["2023-02"] == 3

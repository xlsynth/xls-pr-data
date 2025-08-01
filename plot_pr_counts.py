#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

"""
Generate a bar chart of XLSynth PR counts per month.

The script reads the cached CSV generated by ``accumulate_pr_data.py`` and
filters to pull-requests whose ``head_repo`` is exactly ``xlsynth/xlsynth`` – the
same criteria used by ``plot_pr_delays.py``.  It then counts the number of PRs
opened in each calendar month (UTC) and writes the resulting bar chart to
``pr_counts.png``.

Run:

    $ python plot_pr_counts.py

Requirements: ``pandas`` and ``matplotlib`` which are already declared in
``requirements.txt``.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt


CSV_FILE = Path("pr_data.csv")
META_FILE = Path("pr_data_meta.json")
PLOT_FILE = Path("pr_counts.png")
FILTER_REPO = "xlsynth/xlsynth"


def load_metadata_timestamp() -> datetime:
    """Return the timestamp of the last data scrape for annotation purposes."""
    if META_FILE.exists():
        try:
            with META_FILE.open() as f:
                meta = json.load(f)
            return pd.to_datetime(meta.get("last_scrape"), utc=True).to_pydatetime()
        except Exception:
            pass
    # Fallback – use current UTC time.
    return datetime.utcnow()


def prepare_dataframe() -> pd.DataFrame:
    """Read the PR CSV and return a dataframe filtered to the desired head repo."""
    if not CSV_FILE.exists():
        raise SystemExit(f"CSV file '{CSV_FILE}' not found – run accumulate_pr_data.py first.")

    df = pd.read_csv(CSV_FILE)

    # Keep only PRs from xlsynth/xlsynth.
    df = df[df["head_repo"] == FILTER_REPO]

    # Parse the created_at column into datetimes (UTC assumed).
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)

    # Drop rows where created_at failed to parse.
    df = df[df["created_at"].notna()].copy()

    return df


def count_prs_by_month(df: pd.DataFrame) -> pd.Series:
    """Return a Series indexed by YYYY-MM (string) with PR counts."""
    # Use 
    counts = (
        df["created_at"].dt.to_period("M")
        .value_counts()
        .sort_index()
    )
    # Convert PeriodIndex to string so matplotlib treats them as nominal labels.
    counts.index = counts.index.astype(str)
    return counts


def make_plot(counts: pd.Series, data_timestamp: datetime) -> None:
    """Render and save the bar chart given monthly counts."""
    if counts.empty:
        print("No data after filtering – no plot produced.")
        return

    plt.figure(figsize=(max(10, len(counts) * 0.6), 6))
    plt.bar(counts.index, counts.values, color="skyblue")
    plt.xlabel("Month (YYYY-MM)")
    plt.ylabel("PR count")
    plt.title(
        f"xlsynth/xlsynth PRs opened per month (n={counts.sum()})\nData as of {data_timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(PLOT_FILE)
    print(f"Plot saved as {PLOT_FILE}")


def main() -> None:
    df = prepare_dataframe()
    counts = count_prs_by_month(df)
    ts = load_metadata_timestamp()
    make_plot(counts, ts)


if __name__ == "__main__":
    main()

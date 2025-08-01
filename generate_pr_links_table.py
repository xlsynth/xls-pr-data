#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Update README.md with a month→PR-links table.

The table lists every PR whose ``head_repo`` is ``xlsynth/xlsynth``, grouped by
its creation month (UTC).  Each PR number is rendered as a Markdown link to the
corresponding pull-request on GitHub (``https://github.com/google/xls/pull/<num>``).

The script rewrites *README.md* in-place, replacing the section between the
marker comments::

    <!-- PR_LINKS_TABLE_START -->
    <!-- PR_LINKS_TABLE_END -->

with the freshly generated table.  If the markers are missing, they will be
appended to the end of the document.

Run this script after refreshing ``pr_data.csv`` to keep the README table
current::

    python generate_pr_links_table.py
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from collections import defaultdict

CSV_FILE = Path("pr_data.csv")
README_FILE = Path("README.md")
FILTER_REPO = "xlsynth/xlsynth"
MARKER_START = "<!-- PR_LINKS_TABLE_START -->"
MARKER_END = "<!-- PR_LINKS_TABLE_END -->"


def load_links_by_month() -> dict[str, list[int]]:
    """Return a mapping ``YYYY-MM -> [pr_numbers]`` sorted by month."""
    if not CSV_FILE.exists():
        raise SystemExit(f"CSV file '{CSV_FILE}' not found – run accumulate_pr_data.py first.")

    links_by_month: dict[str, list[int]] = defaultdict(list)
    with CSV_FILE.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["head_repo"] != FILTER_REPO:
                continue
            created_at = row["created_at"]
            if not created_at:
                continue
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            month_key = dt.strftime("%Y-%m")
            links_by_month[month_key].append(int(row["pr_number"]))

    # Sort PR numbers within each month for consistency.
    for num_list in links_by_month.values():
        num_list.sort()

    return dict(sorted(links_by_month.items()))


def build_table(links_by_month: dict[str, list[int]]) -> str:
    """Construct the Markdown table as a multiline string (no trailing newline)."""
    lines: list[str] = ["| Month | PRs |", "| ----- | ---- |"]
    for month, numbers in links_by_month.items():
        links = " ".join(
            f"[#{n}](https://github.com/google/xls/pull/{n})" for n in numbers
        )
        lines.append(f"| {month} | {links} |")
    return "\n".join(lines)


def update_readme(table_md: str, month_count: int) -> None:
    """Replace or append the PR-links table section in README.md."""
    lines = README_FILE.read_text().splitlines()

    try:
        start_idx = lines.index(MARKER_START)
        end_idx = lines.index(MARKER_END)
    except ValueError:
        # Markers are missing – append them to the end.
        lines.extend(["", MARKER_START, MARKER_END])
        start_idx = len(lines) - 2
        end_idx = len(lines) - 1

    # Assemble the replacement block.
    replacement = [MARKER_START] + table_md.splitlines() + [MARKER_END]

    # Build the updated document.
    updated = lines[:start_idx] + replacement + lines[end_idx + 1 :]
    README_FILE.write_text("\n".join(updated) + "\n")
    print(f"README.md updated with table for {month_count} month(s).")


def main() -> None:
    links_by_month = load_links_by_month()
    if not links_by_month:
        print("No XLSynth PRs found – README left unchanged.")
        return
    table_md = build_table(links_by_month)
    update_readme(table_md, len(links_by_month))


if __name__ == "__main__":
    main()

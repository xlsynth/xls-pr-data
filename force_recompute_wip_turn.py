#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Clear cached turn-analysis fields for WIP PR rows in pr_data.csv.

This script does not call GitHub APIs. It only clears cached columns for rows
that are "work in progress" (open, non-draft), so the next run of
`accumulate_pr_data.py` / `update_all.py` recomputes turn state.
"""

import argparse
import csv
from pathlib import Path


def parse_bool_field(raw_value):
    if raw_value is None:
        return False
    text = str(raw_value).strip().lower()
    if text in ("1", "true", "t", "yes", "y"):
        return True
    if text in ("", "0", "false", "f", "no", "n", "none", "null"):
        return False
    raise ValueError(f"Unexpected boolean value: {raw_value!r}")


def is_wip_row(row):
    closed_at = (row.get("closed_at") or "").strip()
    is_open = not closed_at
    is_draft = parse_bool_field(row.get("is_draft"))
    return is_open and not is_draft


def clear_turn_cache_fields(row):
    # Clearing pr_updated_at forces accumulate_pr_data.py to reprocess the PR.
    row["pr_updated_at"] = ""
    row["last_relevant_actor"] = ""
    row["last_relevant_at"] = ""
    row["is_googles_turn"] = ""


def main():
    parser = argparse.ArgumentParser(
        description="Force recomputation of turn state for WIP PR rows."
    )
    parser.add_argument(
        "--csv",
        default="pr_data.csv",
        help="Path to the PR CSV file (default: pr_data.csv).",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"CSV file not found: {csv_path}")

    with csv_path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise SystemExit("CSV has no header/fieldnames.")
        rows = list(reader)

    updated = 0
    for row in rows:
        if is_wip_row(row):
            clear_turn_cache_fields(row)
            updated += 1

    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Cleared turn cache fields for {updated} WIP PR row(s) in {csv_path}.")


if __name__ == "__main__":
    main()

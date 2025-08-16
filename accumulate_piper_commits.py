#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

"""
Scan a git repository for Piper-originated commits and write them to CSV.

We detect Piper commits by the presence of a footer line in the commit body:

    PiperOrigin-RevId: <NUMBER>

For each such commit we record:
  - piper_rev_id: numeric identifier from the footer
  - git_sha: full 40-character git commit SHA
  - author: commit author's display name
  - committed_at: commit author timestamp as ISO-8601 with trailing 'Z' (UTC)

Usage:

    python accumulate_piper_commits.py --repo /path/to/google/xls

If --repo is omitted, the script attempts to use the current working directory
as the target repository. The CSV is written to 'piper_commits.csv' in the
current working directory.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


PIPER_FOOTER_RE = re.compile(r"^PiperOrigin-RevId:\s*(\d+)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class PiperCommit:
    piper_rev_id: str
    git_sha: str
    author: str
    committed_at: str  # ISO8601 UTC with trailing 'Z'


def sanitize_field(field: Optional[str]) -> Optional[str]:
    return field.replace("\r", "").replace("\n", "").strip() if field is not None else field


def sanitize_record(record: dict) -> dict:
    return {k: sanitize_field(v) if isinstance(v, str) else v for k, v in record.items()}


def _run_git(repo: Path, args: List[str]) -> bytes:
    """Run a git command in the given repo and return stdout bytes.

    Raises CalledProcessError on failure.
    """
    cmd = ["git", "-C", str(repo)] + args
    return subprocess.check_output(cmd)


def normalize_to_utc_z(ts: str) -> str:
    """Convert an ISO8601 timestamp with timezone offset to UTC '...Z'."""
    # datetime.fromisoformat supports offsets like +00:00
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        # Assume UTC if no tz given, assert strong invariant otherwise
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def extract_piper_rev_id(commit_body: str) -> Optional[str]:
    """Return the PiperOrigin-RevId number if present in the commit body."""
    m = PIPER_FOOTER_RE.search(commit_body)
    if m:
        return m.group(1)
    return None


def scan_piper_commits(repo: Path) -> List[PiperCommit]:
    """Scan the repo's history for Piper commits and return a sorted list.

    The list is sorted by committed_at descending (newest first).
    """
    # %H=sha, %aI=author date strict ISO8601, %an=author name, %B=body (subject+body)
    # Use unit separators to split fields and record separator between commits.
    pretty = "%H%x1f%aI%x1f%an%x1f%B%x1e"
    raw = _run_git(repo, ["log", "--pretty=format:" + pretty])
    records = raw.decode("utf-8", errors="replace").split("\x1e")

    seen_rev_ids: set[str] = set()
    results: List[PiperCommit] = []
    for rec in records:
        if not rec.strip():
            continue
        try:
            sha, author_date, author_name, body = rec.split("\x1f", 3)
        except ValueError:
            # Ignore malformed records aggressively – invariant should hold for git format
            continue

        rev_id = extract_piper_rev_id(body)
        if not rev_id:
            continue
        if rev_id in seen_rev_ids:
            # Multiple commits with same footer shouldn't occur; keep the first encountered
            continue
        committed_at = normalize_to_utc_z(author_date)
        results.append(PiperCommit(
            piper_rev_id=rev_id,
            git_sha=sha,
            author=author_name,
            committed_at=committed_at,
        ))
        seen_rev_ids.add(rev_id)

    # Sort by timestamp descending so the newest commit becomes row 0 in CSV
    # Use git_sha as a secondary key for deterministic ordering among ties.
    results.sort(key=lambda c: (c.committed_at, c.git_sha), reverse=True)
    return results


def write_csv(commits: Iterable[PiperCommit], csv_path: Path) -> None:
    fieldnames = ["piper_rev_id", "git_sha", "author", "committed_at"]
    rows = [sanitize_record(c.__dict__.copy()) for c in commits]
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Accumulate Piper commits from a git repository.")
    parser.add_argument("--repo", type=str, default=".", help="Path to the target git repository to scan")
    parser.add_argument("--output", type=str, default="piper_commits.csv", help="Output CSV path")
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    if not (repo_path / ".git").exists():
        raise SystemExit(f"Provided --repo path does not appear to be a git repository: {repo_path}")

    logging.info("Scanning repository for Piper commits: %s", repo_path)
    commits = scan_piper_commits(repo_path)
    logging.info("Found %d Piper commits", len(commits))

    out_path = Path(args.output)
    write_csv(commits, out_path)
    logging.info("Wrote %d records to '%s'", len(commits), out_path)


if __name__ == "__main__":
    main()

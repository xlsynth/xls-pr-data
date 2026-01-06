#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0

import generate_pr_links_table


def test_build_table_marks_open_prs_with_emoji(tmp_path, monkeypatch):
    csv_path = tmp_path / "pr_data.csv"
    csv_path.write_text(
        "\n".join(
            [
                "pr_number,head_repo,created_at,is_draft,review_requested_at,reviewing_internally_at,closed_at",
                "199,xlsynth/xlsynth,2026-01-02T05:50:10Z,true,,,",  # open + draft
                "200,xlsynth/xlsynth,2026-01-03T05:50:10Z,false,,,",  # open
                "201,xlsynth/xlsynth,2026-01-03T06:00:00Z,false,,,2026-01-04T00:00:00Z",  # closed
                "150,xlsynth/xlsynth,2025-12-30T18:15:36Z,false,,,2026-01-01T01:02:03Z",  # closed
                "999,google/xls,2026-01-03T05:50:10Z,false,,,",  # filtered out
            ]
        )
        + "\n"
    )
    monkeypatch.setattr(generate_pr_links_table, "CSV_FILE", csv_path)

    links_by_month = generate_pr_links_table.load_links_by_month()
    table_md = generate_pr_links_table.build_table(links_by_month)

    assert table_md == "\n".join(
        [
            "🧪 = draft (open)",
            "🚧 = still open (not merged yet)",
            "",
            "| Month | PRs |",
            "| ----- | ---- |",
            "| 2025-12 | [#150](https://github.com/google/xls/pull/150) |",
            "| 2026-01 | [#199 🧪](https://github.com/google/xls/pull/199) · [#200 🚧](https://github.com/google/xls/pull/200) · [#201](https://github.com/google/xls/pull/201) |",
        ]
    )


def test_build_table_omits_legend_when_no_open_prs(tmp_path, monkeypatch):
    csv_path = tmp_path / "pr_data.csv"
    csv_path.write_text(
        "\n".join(
            [
                "pr_number,head_repo,created_at,is_draft,review_requested_at,reviewing_internally_at,closed_at",
                "150,xlsynth/xlsynth,2025-12-30T18:15:36Z,false,,,2026-01-01T01:02:03Z",
            ]
        )
        + "\n"
    )
    monkeypatch.setattr(generate_pr_links_table, "CSV_FILE", csv_path)

    links_by_month = generate_pr_links_table.load_links_by_month()
    table_md = generate_pr_links_table.build_table(links_by_month)

    assert table_md == "\n".join(
        [
            "| Month | PRs |",
            "| ----- | ---- |",
            "| 2025-12 | [#150](https://github.com/google/xls/pull/150) |",
        ]
    )

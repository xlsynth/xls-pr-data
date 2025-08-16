# SPDX-License-Identifier: Apache-2.0

from accumulate_piper_commits import extract_piper_rev_id, normalize_to_utc_z


def test_extract_piper_rev_id_basic():
    body = """
Some summary line

More details...

PiperOrigin-RevId: 456789123

Change-Id: Ideadbeef
""".strip()
    assert extract_piper_rev_id(body) == "456789123"


def test_extract_piper_rev_id_absent():
    body = """
Commit without the desired footer
""".strip()
    assert extract_piper_rev_id(body) is None


def test_normalize_to_utc_z_keeps_utc():
    assert normalize_to_utc_z("2024-10-01T12:34:56+00:00") == "2024-10-01T12:34:56Z"


def test_normalize_to_utc_z_converts_offset():
    # 12:34:56 +05:30 should become 07:04:56Z
    assert normalize_to_utc_z("2024-10-01T12:34:56+05:30") == "2024-10-01T07:04:56Z"

#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import unittest
import accumulate_pr_data


class TestProcessPR(unittest.TestCase):
    def test_process_pr_immutable_first_lifecycle(self):
        # Override fetch_timeline_events to simulate multiple lifecycle events
        def fake_fetch_timeline_events(pr_number):
            return [
                {"event": "review_requested", "created_at": "2023-01-01T12:00:00Z"},
                {"event": "labeled", "label": {"name": "reviewing internally"}, "created_at": "2023-01-01T13:00:00Z"},
                {"event": "closed", "created_at": "2023-01-01T14:00:00Z"},
                {"event": "reopened", "created_at": "2023-01-02T10:00:00Z"},
                {"event": "closed", "created_at": "2023-01-02T12:00:00Z"},
            ]
        accumulate_pr_data.fetch_timeline_events = fake_fetch_timeline_events

        pr = {
            "number": 123,
            "created_at": "2023-01-01T10:00:00Z",
            "closed_at": "2023-01-02T12:00:00Z",
            "head": {"repo": {"full_name": "xlsynth/xlsynth"}}
        }
        processed = accumulate_pr_data.process_pr(pr)

        # Expected to capture only the first lifecycle events
        self.assertEqual(processed["review_requested_at"], "2023-01-01T12:00:00Z")
        self.assertEqual(processed["reviewing_internally_at"], "2023-01-01T13:00:00Z")
        self.assertEqual(processed["closed_at"], "2023-01-01T14:00:00Z")
        self.assertEqual(processed["head_repo"], "xlsynth/xlsynth")


if __name__ == '__main__':
    unittest.main()

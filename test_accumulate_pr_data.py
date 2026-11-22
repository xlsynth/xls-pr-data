#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import unittest
import accumulate_pr_data
from unittest import mock


class TestProcessPR(unittest.TestCase):
    def test_process_pr_immutable_first_lifecycle(self):
        events = [
            {"event": "review_requested", "created_at": "2023-01-01T12:00:00Z"},
            {"event": "labeled", "label": {"name": "reviewing internally"}, "created_at": "2023-01-01T13:00:00Z"},
            {"event": "closed", "created_at": "2023-01-01T14:00:00Z"},
            {"event": "reopened", "created_at": "2023-01-02T10:00:00Z"},
            {"event": "closed", "created_at": "2023-01-02T12:00:00Z"},
        ]

        pr = {
            "number": 123,
            "created_at": "2023-01-01T10:00:00Z",
            "closed_at": "2023-01-02T12:00:00Z",
            "head": {"repo": {"full_name": "xlsynth/xlsynth"}}
        }
        with mock.patch.object(accumulate_pr_data, "fetch_all_events", return_value=events):
            processed = accumulate_pr_data.process_pr(pr)

        # Expected to capture only the first lifecycle events
        self.assertEqual(processed["review_requested_at"], "2023-01-01T12:00:00Z")
        self.assertEqual(processed["reviewing_internally_at"], "2023-01-01T13:00:00Z")
        self.assertEqual(processed["closed_at"], "2023-01-01T14:00:00Z")
        self.assertEqual(processed["head_repo"], "xlsynth/xlsynth")
        self.assertFalse(processed["is_draft"])

    def test_draft_uses_only_timeline_events(self):
        timeline = [
            {"event": "closed", "created_at": "2023-01-03T10:00:00Z"},
            {"event": "review_requested", "created_at": "2023-01-02T10:00:00Z"},
        ]
        for closed_at in (None, "2023-01-03T10:00:00Z"):
            with self.subTest(closed_at=closed_at):
                pr = {"number": 123, "created_at": "2023-01-01T10:00:00Z",
                      "draft": True, "closed_at": closed_at}
                events = timeline if closed_at else []
                with mock.patch.object(accumulate_pr_data, "fetch_timeline_events", return_value=events), \
                     mock.patch.object(accumulate_pr_data, "fetch_supplemental_turn_events") as supplemental:
                    record = accumulate_pr_data.process_pr(pr)
                supplemental.assert_not_called()
                self.assertEqual(record["review_requested_at"], "2023-01-02T10:00:00Z" if closed_at else None)
                self.assertEqual(record["closed_at"], closed_at)
                self.assertIsNone(record["is_googles_turn"])

    def test_closed_non_draft_uses_earliest_review_before_first_close(self):
        pr = {"number": 123, "created_at": "2023-01-01T10:00:00Z", "closed_at": "2023-01-05T10:00:00Z"}
        timeline = [
            {"event": "closed", "created_at": "2023-01-04T10:00:00Z"},
            {"event": "reviewed", "created_at": "2023-01-03T10:00:00Z"},
        ]
        reviews = [{"submitted_at": "2023-01-02T10:00:00Z"}]
        with mock.patch.object(accumulate_pr_data, "fetch_timeline_events", return_value=timeline), \
             mock.patch.object(accumulate_pr_data, "fetch_paginated_json", return_value=reviews) as get:
            record = accumulate_pr_data.process_pr(pr)
        get.assert_called_once()
        self.assertIn("/pulls/123/reviews?", get.call_args.args[0])
        self.assertEqual(record["review_requested_at"], "2023-01-02T10:00:00Z")
        self.assertEqual(record["closed_at"], "2023-01-04T10:00:00Z")
        self.assertIsNone(record["is_googles_turn"])


class TestTurnDetection(unittest.TestCase):
    def test_latest_approval_means_googles_turn(self):
        events = [
            {
                "event": "review_submitted",
                "created_at": "2023-01-01T12:00:00Z",
                "actor": {"login": "googler"},
                "state": "APPROVED",
            },
        ]
        with mock.patch.object(accumulate_pr_data, "is_xlsynth_org_member", return_value=False):
            is_turn, last_actor, last_at = accumulate_pr_data.get_turn_state(
                events=events,
                pr_author_login="author",
                membership_cache={},
            )
        self.assertTrue(is_turn)
        self.assertEqual(last_actor, "googler")
        self.assertEqual(last_at, "2023-01-01T12:00:00Z")

    def test_author_push_after_feedback_does_not_clear_feedback_blocker(self):
        events = [
            {
                "event": "review_submitted",
                "created_at": "2023-01-01T12:00:00Z",
                "actor": {"login": "googler"},
            },
            {
                "event": "committed",
                "created_at": "2023-01-01T12:30:00Z",
                "actor": {"login": "author"},
            },
        ]
        membership_cache = {}
        with mock.patch.object(accumulate_pr_data, "is_xlsynth_org_member") as member_lookup:
            member_lookup.side_effect = lambda login, _cache: {"googler": False, "author": True}.get(login)
            is_turn, last_actor, last_at = accumulate_pr_data.get_turn_state(
                events=events,
                pr_author_login="author",
                membership_cache=membership_cache,
            )
        self.assertFalse(is_turn)
        self.assertEqual(last_actor, "author")
        self.assertEqual(last_at, "2023-01-01T12:30:00Z")

    def test_author_force_push_after_feedback_does_not_clear_feedback_blocker(self):
        events = [
            {
                "event": "review_submitted",
                "created_at": "2023-01-01T12:00:00Z",
                "actor": {"login": "googler"},
            },
            {
                "event": "head_ref_force_pushed",
                "created_at": "2023-01-01T12:30:00Z",
                "actor": {"login": "author"},
            },
        ]
        membership_cache = {}
        with mock.patch.object(accumulate_pr_data, "is_xlsynth_org_member") as member_lookup:
            member_lookup.side_effect = lambda login, _cache: {"googler": False, "author": True}.get(login)
            is_turn, last_actor, last_at = accumulate_pr_data.get_turn_state(
                events=events,
                pr_author_login="author",
                membership_cache=membership_cache,
            )
        self.assertFalse(is_turn)
        self.assertEqual(last_actor, "author")
        self.assertEqual(last_at, "2023-01-01T12:30:00Z")

    def test_label_after_approval_does_not_change_turn(self):
        events = [
            {
                "event": "review_submitted",
                "created_at": "2023-01-01T12:00:00Z",
                "actor": {"login": "googler"},
                "state": "APPROVED",
            },
            {
                "event": "labeled",
                "created_at": "2023-01-01T12:01:00Z",
                "actor": {"login": "googler"},
                "label": {"name": "Reviewing Internally"},
            },
        ]
        with mock.patch.object(accumulate_pr_data, "is_xlsynth_org_member", return_value=False):
            is_turn, last_actor, last_at = accumulate_pr_data.get_turn_state(
                events=events,
                pr_author_login="author",
                membership_cache={},
            )
        self.assertTrue(is_turn)
        self.assertEqual(last_actor, "googler")
        self.assertEqual(last_at, "2023-01-01T12:00:00Z")

    def test_unresolved_googler_feedback_takes_precedence(self):
        events = [
            {
                "event": "review_submitted",
                "created_at": "2023-01-01T12:00:00Z",
                "actor": {"login": "googler"},
            },
            {
                "event": "committed",
                "created_at": "2023-01-01T12:30:00Z",
                "actor": {"login": "author"},
            },
            {
                "event": "review_submitted",
                "created_at": "2023-01-01T13:00:00Z",
                "actor": {"login": "googler"},
            },
        ]
        with mock.patch.object(accumulate_pr_data, "is_xlsynth_org_member") as member_lookup:
            member_lookup.side_effect = lambda login, _cache: {"googler": False, "author": True}.get(login)
            is_turn, _, _ = accumulate_pr_data.get_turn_state(
                events=events,
                pr_author_login="author",
                membership_cache={},
            )
        self.assertFalse(is_turn)

    def test_explicit_resolution_clears_feedback_blocker(self):
        events = [
            {
                "event": "review_submitted",
                "created_at": "2023-01-01T12:00:00Z",
                "actor": {"login": "googler"},
            },
            {
                "event": "review_thread_resolved",
                "created_at": "2023-01-01T12:10:00Z",
            },
            {
                "event": "commented",
                "created_at": "2023-01-01T12:20:00Z",
                "actor": {"login": "external"},
            },
        ]
        with mock.patch.object(accumulate_pr_data, "is_xlsynth_org_member") as member_lookup:
            member_lookup.side_effect = lambda login, _cache: {"googler": False, "external": True}.get(login)
            is_turn, last_actor, _ = accumulate_pr_data.get_turn_state(
                events=events,
                pr_author_login="author",
                membership_cache={},
            )
        self.assertTrue(is_turn)
        self.assertEqual(last_actor, "external")

    def test_author_reply_comment_clears_feedback_blocker(self):
        events = [
            {
                "event": "review_submitted",
                "created_at": "2023-01-01T12:00:00Z",
                "actor": {"login": "googler"},
            },
            {
                "event": "commented",
                "created_at": "2023-01-01T12:10:00Z",
                "actor": {"login": "author"},
            },
        ]
        with mock.patch.object(accumulate_pr_data, "is_xlsynth_org_member") as member_lookup:
            member_lookup.side_effect = lambda login, _cache: {"googler": False, "author": True}.get(login)
            is_turn, last_actor, _ = accumulate_pr_data.get_turn_state(
                events=events,
                pr_author_login="author",
                membership_cache={},
            )
        self.assertTrue(is_turn)
        self.assertEqual(last_actor, "author")

    def test_author_review_request_clears_feedback_blocker(self):
        events = [
            {
                "event": "review_submitted",
                "created_at": "2023-01-01T12:00:00Z",
                "actor": {"login": "googler"},
            },
            {
                "event": "review_requested",
                "created_at": "2023-01-01T12:10:00Z",
                "actor": {"login": "author"},
            },
        ]
        with mock.patch.object(accumulate_pr_data, "is_xlsynth_org_member") as member_lookup:
            member_lookup.side_effect = lambda login, _cache: {"googler": False, "author": True}.get(login)
            is_turn, last_actor, last_at = accumulate_pr_data.get_turn_state(
                events=events,
                pr_author_login="author",
                membership_cache={},
            )
        self.assertTrue(is_turn)
        self.assertEqual(last_actor, "author")
        self.assertEqual(last_at, "2023-01-01T12:10:00Z")

    def test_non_xlsynth_reviewer_blocks_turn(self):
        events = [
            {
                "event": "review_submitted",
                "created_at": "2023-01-01T12:00:00Z",
                "actor": {"login": "non_xlsynth_reviewer"},
            },
            {
                "event": "committed",
                "created_at": "2023-01-01T12:10:00Z",
                "actor": {"login": "author"},
            },
            {
                "event": "review_submitted",
                "created_at": "2023-01-01T12:20:00Z",
                "actor": {"login": "non_xlsynth_reviewer"},
            },
        ]
        with mock.patch.object(accumulate_pr_data, "is_xlsynth_org_member", return_value=False):
            is_turn, _, _ = accumulate_pr_data.get_turn_state(
                events=events,
                pr_author_login="author",
                membership_cache={},
            )
        self.assertFalse(is_turn)

    def test_process_pr_sets_new_schema_fields(self):
        pr = {
            "number": 123,
            "created_at": "2023-01-01T10:00:00Z",
            "updated_at": "2023-01-01T12:00:00Z",
            "draft": False,
            "closed_at": None,
            "user": {"login": "author"},
            "head": {"repo": {"full_name": "xlsynth/xlsynth"}},
        }
        events = [
            {
                "event": "commented",
                "created_at": "2023-01-01T11:00:00Z",
                "actor": {"login": "external"},
            }
        ]
        with mock.patch.object(accumulate_pr_data, "fetch_all_events", return_value=events):
            with mock.patch.object(accumulate_pr_data, "is_xlsynth_org_member", return_value=True):
                processed = accumulate_pr_data.process_pr(pr, membership_cache={})

        self.assertEqual(processed["pr_updated_at"], "2023-01-01T12:00:00Z")
        self.assertEqual(processed["last_relevant_actor"], "external")
        self.assertEqual(processed["last_relevant_at"], "2023-01-01T11:00:00Z")
        self.assertTrue(processed["is_googles_turn"])


class TestLatency(unittest.TestCase):
    def test_get_pr_landing_latency_excludes_draft(self):
        record = {
            "pr_number": 123,
            "is_draft": True,
            "review_requested_at": "2023-01-01T12:00:00Z",
            "closed_at": "2023-01-01T14:00:00Z",
        }
        self.assertIsNone(accumulate_pr_data.get_pr_landing_latency(record))


if __name__ == '__main__':
    unittest.main()

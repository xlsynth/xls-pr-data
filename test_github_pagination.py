#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import json
import unittest
from unittest import mock

import requests

import accumulate_pr_data as collector


PULLS_URL = "https://api.github.com/repos/google/xls/pulls?state=all&per_page=100"
NEXT_PAGE = "https://api.github.com/repositories/268911282/pulls?after=cursor"


def github_response(status, body, headers=None, url=PULLS_URL):
    response = requests.Response()
    response.status_code = status
    response.url = url
    response.headers.update(headers or {})
    response._content = json.dumps(body).encode()
    return response


class TestGitHubPagination(unittest.TestCase):
    def test_follows_next_link_and_stops_after_last_page(self):
        responses = [
            github_response(200, [1], {"Link": f'<{NEXT_PAGE}>; rel="next"'}),
            github_response(200, [2], {"Link": f'<{PULLS_URL}>; rel="prev"'}, url=NEXT_PAGE),
        ]
        with mock.patch("requests.get", side_effect=responses) as get:
            self.assertEqual(collector.fetch_paginated_json(PULLS_URL, {}), [1, 2])
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[1].args[0], NEXT_PAGE)

    def test_pr_page_limit_stops_before_following_next_link(self):
        first = github_response(200, [{"number": 42}], {"Link": f'<{NEXT_PAGE}>; rel="next"'})
        with mock.patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}):
            with mock.patch("requests.get", return_value=first) as get:
                self.assertEqual(collector.fetch_prs(max_pages=1), [{"number": 42}])
        get.assert_called_once()

    def test_relative_next_link_resolves_against_github(self):
        relative = "/repositories/268911282/pulls?after=cursor"
        responses = [
            github_response(200, [1], {"Link": f'<{relative}>; rel="next"'}),
            github_response(200, [2], url=NEXT_PAGE),
        ]
        with mock.patch("requests.get", side_effect=responses) as get:
            self.assertEqual(collector.fetch_paginated_json(PULLS_URL, {}), [1, 2])
        self.assertEqual(get.call_args_list[1].args[0], NEXT_PAGE)

    def test_cross_origin_next_link_stops_before_sending_credentials(self):
        first = github_response(200, [1], {"Link": '<https://other.example/api>; rel="next"'})
        with mock.patch("requests.get", return_value=first) as get:
            with self.assertRaises(ValueError):
                collector.fetch_paginated_json(PULLS_URL, {"Authorization": "token test-token"})
        get.assert_called_once()


class TestGitHubRateLimits(unittest.TestCase):
    def test_primary_limit_retries_same_page_and_keeps_previous_items(self):
        responses = [
            github_response(200, [1], {"Link": f'<{NEXT_PAGE}>; rel="next"'}),
            github_response(
                403, {"message": "API rate limit exceeded"},
                {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "120"}, url=NEXT_PAGE,
            ),
            github_response(200, [2], url=NEXT_PAGE),
        ]
        with mock.patch("time.time", return_value=100), mock.patch("time.sleep") as sleep:
            with mock.patch("requests.get", side_effect=responses) as get:
                self.assertEqual(collector.fetch_paginated_json(PULLS_URL, {}), [1, 2])
        sleep.assert_called_once_with(21)
        self.assertEqual([call.args[0] for call in get.call_args_list[1:]], [NEXT_PAGE, NEXT_PAGE])

    def test_membership_retries_throttling_before_caching_result(self):
        responses = [
            github_response(429, {"message": "Too many requests"}, {"Retry-After": "7"}),
            github_response(204, None),
        ]
        cache = {}
        with mock.patch("time.sleep") as sleep, mock.patch("requests.get", side_effect=responses) as get:
            self.assertIs(collector.is_xlsynth_org_member("someone", cache), True)
            self.assertIs(collector.is_xlsynth_org_member("someone", cache), True)
        sleep.assert_called_once_with(7)
        self.assertEqual(get.call_count, 2)

    def test_secondary_limit_uses_bounded_exponential_backoff(self):
        limited = github_response(403, {"message": "You have exceeded a secondary rate limit."})
        with mock.patch("time.sleep") as sleep, mock.patch("requests.get", return_value=limited) as get:
            with self.assertRaises(requests.HTTPError):
                collector.fetch_paginated_json(PULLS_URL, {})
        self.assertEqual(sleep.call_args_list, [mock.call(60), mock.call(120), mock.call(240)])
        self.assertEqual(get.call_count, 4)

    def test_ordinary_forbidden_response_preserves_endpoint_behavior(self):
        forbidden = github_response(403, {"message": "Resource not accessible by integration"})
        with mock.patch("time.sleep") as sleep, mock.patch("requests.get", return_value=forbidden) as get:
            with self.assertRaises(requests.HTTPError):
                collector.fetch_paginated_json(PULLS_URL, {})
            cache = {}
            self.assertIsNone(collector.is_xlsynth_org_member("someone", cache))
            self.assertEqual(cache, {"someone": None})
        sleep.assert_not_called()
        self.assertEqual(get.call_count, 2)


if __name__ == "__main__":
    unittest.main()

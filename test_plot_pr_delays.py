# SPDX-License-Identifier: Apache-2.0

import datetime
import pytz
from plot_pr_delays import effective_review_time

PT = pytz.timezone("America/Los_Angeles")

def test_review_request_adjustment_thurs_2am():
    # Given a review request at 2 AM on a Thursday (in Pacific Time)
    # For example, use Thursday, September 9, 2021 at 2:00 AM PT.
    review_request_time = PT.localize(datetime.datetime(2021, 9, 9, 2, 0, 0))

    # When computing the effective review time (i.e. when the latency counter starts)
    effective_time = effective_review_time(review_request_time)

    # Then we expect the effective review time to be 9 AM on the following Friday.
    # That is, Friday, September 10, 2021 at 9:00 AM PT.
    expected_time = PT.localize(datetime.datetime(2021, 9, 10, 9, 0, 0))

    # Convert the effective time to Pacific Time for comparison.
    effective_time_pt = effective_time.astimezone(PT)

    assert effective_time_pt == expected_time, (
        f"Expected effective review time to be {expected_time}, but got {effective_time_pt}"
    )

def test_review_request_no_adjustment_friday_9am():
    """A review request on Friday at 9am should remain unchanged."""
    friday_review_time = PT.localize(datetime.datetime(2021, 9, 10, 9, 0, 0))
    friday_effective_time = effective_review_time(friday_review_time)
    friday_expected_time = friday_review_time  # Expect no adjustment; remains 9:00 AM PT.
    friday_effective_time_pt = friday_effective_time.astimezone(PT)
    assert friday_effective_time_pt == friday_expected_time, (
        f"Expected effective review time to remain {friday_expected_time}, but got {friday_effective_time_pt}"
    )

def test_review_request_no_adjustment_friday_noon():
    """A review request on Friday at noon should remain unchanged."""
    friday_review_time = PT.localize(datetime.datetime(2021, 9, 10, 12, 0, 0))
    friday_effective_time = effective_review_time(friday_review_time)
    friday_expected_time = friday_review_time  # Expect no adjustment; remains noon pacific
    friday_effective_time_pt = friday_effective_time.astimezone(PT)
    assert friday_effective_time_pt == friday_expected_time, (
        f"Expected effective review time to remain {friday_expected_time}, but got {friday_effective_time_pt}"
    )

def test_review_request_after_noon_friday_kicked_to_monday():
    """A review request at 12:01pm on Friday (Pacific Time) should get bumped to Monday 9am."""
    review_request_time = PT.localize(datetime.datetime(2021, 9, 10, 12, 1, 0))

    # When computing the effective review time using effective_review_time
    effective_time = effective_review_time(review_request_time)

    # Then the effective review time should be Monday at 9:00 AM (Pacific Time)
    expected_time = PT.localize(datetime.datetime(2021, 9, 13, 9, 0, 0))
    effective_time_pt = effective_time.astimezone(PT)
    assert effective_time_pt == expected_time, (
        f"Expected effective review time to be {expected_time}, but got {effective_time_pt}"
    )

def test_review_request_after_noon_on_monday_kicked_to_tuesday():
    """A review request at 12:01pm on Monday should get bumped to Tuesday 9am."""
    review_request_time = PT.localize(datetime.datetime(2021, 9, 13, 12, 1, 0))
    effective_time = effective_review_time(review_request_time)
    expected_time = PT.localize(datetime.datetime(2021, 9, 14, 9, 0, 0))
    effective_time_pt = effective_time.astimezone(PT)
    assert effective_time_pt == expected_time, (
        f"Expected effective review time on Monday 12:01 to be {expected_time}, but got {effective_time_pt}"
    )

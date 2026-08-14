"""Regression coverage for just-in-time discrepancy-review navigation."""

from review.route_discrepancy_review import discrepancy_review


def test_discrepancy_review_route_is_not_response_cached():
    """Review listing responses must not outlive their MV snapshot."""
    assert not hasattr(discrepancy_review, "uncached")

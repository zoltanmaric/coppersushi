"""Delegation scores use completed runner calls."""

import unittest

from replay import routing_passes


class RoutingTest(unittest.TestCase):
    def test_claimed_or_failed_work_does_not_count(self):
        failed = {"id": "specialist-1", "assignment": "trace writes", "status": "failed"}
        lead = {"id": "lead", "status": "completed"}
        self.assertFalse(routing_passes("some", [lead, failed]))
        self.assertFalse(routing_passes("solo", [lead, failed]))
        self.assertTrue(routing_passes("solo", [lead]))

    def test_two_reviews_require_distinct_completed_assignments(self):
        first = {"id": "specialist-1", "assignment": "trace writes", "status": "completed"}
        second = {**first, "id": "specialist-2"}
        self.assertFalse(routing_passes("two", [first, second]))
        self.assertTrue(routing_passes("two", [first, {**second, "assignment": "trace reads"}]))

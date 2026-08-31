"""Test common mixins."""
import re

import pytest
from django.core.exceptions import ValidationError
from django.test import TestCase
from model_bakery import baker

from sil_advantage.visits.models import Visit


class TestTransitionValidationMixin(TestCase):
    """Test Transition Validation Mixin."""

    def test_proper_transition(self):
        """Test a valid state change."""
        visit = baker.make(Visit, status="PLANNED")
        logs = visit.state_transition_logs.values_list(
            "status", "status_from", "status_to"
        )
        self.assertEqual([], list(logs))
        visit.status = "ARRIVED"
        visit.save()
        logs = visit.state_transition_logs.values_list(
            "status", "status_from", "status_to"
        )
        self.assertEqual([("ARRIVED", "PLANNED", "ARRIVED")], list(logs))

    def test_invalid_transition(self):
        """Test an invalid state change."""
        visit = baker.make(Visit, status="IN_PROGRESS")
        exp_msg = re.escape(
            "{'status': ['Invalid transition from IN_PROGRESS to CANCELLED']}"
        )
        with pytest.raises(ValidationError, match=exp_msg):
            visit.status = "CANCELLED"
            visit.save()
        visit.refresh_from_db()
        self.assertEqual("IN_PROGRESS", visit.status)

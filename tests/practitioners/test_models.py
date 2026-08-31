"""Test for the practitioner models."""
from unittest import TestCase

import pytest
from django.core.exceptions import ValidationError
from model_bakery import baker

from sil_advantage.common.models.common_models import Person
from sil_advantage.practitioners.models import Practitioner
from tests.common.test_common_views import global_organisation


@pytest.mark.usefixtures("organisation")
class PractitionerTest(TestCase):
    """Tests for Practitioner."""

    def setUp(self):
        """Setup test environment."""
        self.organisation = global_organisation()
        self.person = baker.make(
            Person,
            title="Dr",
            first_name="John",
            other_names="Njuguna",
            last_name="Doe",
        )

    def test_unicode(self):
        """Test for unicode."""
        practitioner = baker.make(
            Practitioner,
            person=self.person,
        )
        expected = "{} {}".format(
            practitioner.person.title,
            practitioner.person.get_full_name(),
        )
        assert str(practitioner) == expected

    def test_one_to_one_relationship(self):
        """Test enforcment of OneToOne Relationship."""
        baker.make(
            Practitioner,
            person=self.person,
        )
        with pytest.raises(ValidationError) as exc:
            baker.make(
                Practitioner,
                person=self.person,
            )
        assert (
            str(exc.value)
            == "{'person': ['Practitioner with this Person already exists.']}"
        )

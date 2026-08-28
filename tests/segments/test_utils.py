"""Test segments utils."""
import pytest
from model_bakery import baker

from sil_advantage.common.models import Person
from sil_advantage.patients.models import Patient
from sil_advantage.segments.models.template_variables import (
    get_fields_and_properties_data,
)

pytestmark = pytest.mark.django_db


def test_get_fields_and_properties_data(organisation, organisation_user):
    """Test retrieving data from a person."""
    person = baker.make(
        Person,
        organisation=organisation,
        created_by=organisation_user.id,
        title="Mister",
        first_name="Pepe",
        other_names="Julian",
        last_name="Onziema",
    )

    baker.make(
        Patient,
        person=person,
        organisation=organisation,
        created_by=organisation_user.id,
        global_health_id="1234098745673421",
    )

    data = get_fields_and_properties_data(Person, person)

    # field data
    assert data["title"] == "Mister"
    assert data["first_name"] == "Pepe"
    assert data["other_names"] == "Julian"
    assert data["last_name"] == "Onziema"

    # property data
    assert data["global_health_id"] == "1234098745673421"

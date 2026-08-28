"""Template variables."""
from dataclasses import dataclass
from typing import Set

from django.db import models
from django.db.models import Model, base
from django.forms.models import model_to_dict
from django.utils.functional import cached_property

from sil_advantage.common.cache import cached
from sil_advantage.common.models import Person

from .segments import SegmentMember, SegmentUpload


class TemplateVariableCategory(models.TextChoices):
    """Available message template variables category."""

    PROFILE = "PROFILE", "Person's Profile"
    OTHER = "OTHER", "Additional Information"


@dataclass
class MessageTemplateVariable:
    """Class representing a template variable."""

    name: str
    category: str
    variable: str


variables = [
    {
        "name": "Title",
        "variable": "{{title}}",
        "category": TemplateVariableCategory.PROFILE,
    },
    {
        "name": "First Name",
        "variable": "{{first_name}}",
        "category": TemplateVariableCategory.PROFILE,
    },
    {
        "name": "Last Name",
        "variable": "{{last_name}}",
        "category": TemplateVariableCategory.PROFILE,
    },
    {
        "name": "Date of Birth",
        "variable": "{{date_of_birth}}",
        "category": TemplateVariableCategory.PROFILE,
    },
]


def template_variable_constants() -> list[MessageTemplateVariable]:
    """Template variable constants."""
    return [MessageTemplateVariable(**var) for var in variables]


@cached(ttl=600)
def get_extra_template_variables(
    segment_ids: list[str],
) -> list[MessageTemplateVariable]:
    """Gets extra template variables.

    Args:
        *args: Variable positional arguments.
            - segment_ids: Segment IDs belonging to Segments.

    Returns:
        list[MessageTemplateVariable]: A list of extra template variables
        that are accessible when sending messages to a segment.
    """
    variables = []
    extra_variables: Set[str] = set()

    uploads = SegmentUpload.objects.filter(
        segment__in=segment_ids, extra_headers__len__gt=0
    ).all()

    for upload in uploads:
        extra_variables.update(upload.extra_headers)  # type: ignore

    for extra_variable in extra_variables:
        d = {
            "name": str(extra_variable.title().replace("_", " ")),
            "variable": f"{{{{{extra_variable}}}}}",
            "category": TemplateVariableCategory.OTHER,
        }
        var = MessageTemplateVariable(**d)
        variables.append(var)

    return variables


def get_fields_and_properties_data(
    model: base.ModelBase, instance: Model
) -> dict[str, str | int]:
    """Returns a dict containing all the data in instance.

    Data in model property attribute should be int or string
    """
    data = {}

    data.update(model_to_dict(instance))

    property_names = [
        name
        for name in dir(model)
        if isinstance(getattr(model, name), (property, cached_property))
    ]

    for name in property_names:
        if not isinstance(getattr(instance, name), (int, str)):
            continue

        data[name] = getattr(instance, name)

    return data


def generate_context_data(member: SegmentMember) -> dict[str, str | int]:
    """Generates context data used to render a template."""
    context = {}

    person_data = get_fields_and_properties_data(Person, member.person)
    context.update(person_data)

    if member.extra_data:
        context.update(member.extra_data)

    # remove 'None' values
    return {key: value for key, value in context.items() if value is not None}

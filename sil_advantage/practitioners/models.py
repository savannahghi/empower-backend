"""Practitioner models."""
from django.db import models

from sil_advantage.common.models.base import AbstractBase
from sil_advantage.common.models.common_models import Person
from sil_advantage.common.models.mixins import OrgUnitIdsMixin
from sil_advantage.scheduling import PRACTITIONER_TYPES


class Practitioner(AbstractBase, OrgUnitIdsMixin):  # type: ignore[django-manager-missing]
    """This model represents a health practitioner's profile."""

    person = models.OneToOneField(
        Person,
        on_delete=models.PROTECT,
        related_name="practitioner",
    )
    qualification = models.CharField(
        max_length=255,
        choices=PRACTITIONER_TYPES,
    )

    def __str__(self) -> str:
        """Represent a practitioner using their title and names."""
        return "{} {}".format(self.person.title, self.person.get_full_name())

"""Journey models."""
from django.db import models
from sil_cacheable.orm import CacheableManager
from tree_queries.models import TreeNode

from sil_advantage.common.models.base import AbstractBase
from sil_advantage.common.models.common_models import Person
from sil_advantage.common.models.mixins import OrgUnitIdsMixin
from sil_advantage.segments.models.filters import (
    Filter,
    FilterAllowedOperations,
)
from sil_advantage.segments.models.segments import Segment, SegmentMember


class JourneyMemberStatus(models.TextChoices):
    """Attributes that define the status of a segment."""

    ACTIVE = "ACTIVE", "Member in active state within journey"
    RETIRED = "RETIRED", "Member in retired state within journey"


class Journey(OrgUnitIdsMixin, AbstractBase):  # type: ignore[django-manager-missing]
    """A journey."""

    name = models.CharField(max_length=48)
    description = models.CharField(max_length=256, blank=True, null=True)

    objects: models.Manager["Journey"] = CacheableManager()

    def __str__(self) -> str:
        """String representation of a Journey."""
        return self.name

    class Meta:
        """Set model options."""

        ordering = ("-updated", "-created")


class JourneySegment(OrgUnitIdsMixin, AbstractBase, TreeNode):  # type: ignore[django-manager-missing]
    """Link between a journey and segment."""

    journey = models.ForeignKey(
        Journey,
        on_delete=models.PROTECT,
        related_name="journey_segments",
    )
    segment = models.ForeignKey(
        Segment,
        on_delete=models.PROTECT,
    )

    objects: models.Manager["JourneySegment"] = CacheableManager()

    class Meta(AbstractBase.Meta):
        """Set model options."""

        unique_together = [["journey", "segment"]]


class JourneyMember(OrgUnitIdsMixin, AbstractBase):
    """Link a person to a journey."""

    journey = models.ForeignKey(
        Journey,
        on_delete=models.PROTECT,
        related_name="journey_members",
    )
    person = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="journey_memberships"
    )
    current_stage = models.ForeignKey(SegmentMember, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=64,
        choices=JourneyMemberStatus.choices,
        default=JourneyMemberStatus.ACTIVE,
    )

    objects: models.Manager["JourneyMember"] = CacheableManager()

    class Meta:
        """Set model options."""

        unique_together = [["journey", "person"]]
        ordering = ("-updated", "-created")


class JourneyAttributes(OrgUnitIdsMixin, AbstractBase):
    """Store filters belonging to a journey."""

    journey = models.ForeignKey(
        Journey,
        on_delete=models.PROTECT,
        related_name="journey_attributes",
    )
    filter = models.ForeignKey(Filter, on_delete=models.CASCADE)
    operation = models.CharField(
        max_length=64,
        choices=FilterAllowedOperations.choices,
        help_text="the operation to be applied to this filter within the journey.",
    )
    value = models.CharField(max_length=256)

    objects: models.Manager["JourneyAttributes"] = CacheableManager()

"""Handles ussd segment functionalities.

Classes:
    SegmentManager: Provides methods to get organisation segments and add
    persons to segments.
"""
import logging
from typing import Any, List

from sil_advantage.common.models import Person
from sil_advantage.notifications.ussd.managers.common_manager import (
    CommonFieldsManager,
)
from sil_advantage.segments.models import Segment, SegmentMember

logger = logging.getLogger(__name__)


class SegmentManager:
    """Provides methods to get organisation segments and add persons to segments."""

    def __init__(self, code: Any):
        """Initialize."""
        self.common_fields_manager = CommonFieldsManager(code)
        self.common_fields = self.common_fields_manager.get_common_fields()

    @staticmethod
    def get_available_segments_for_person(person: Person) -> List[str]:
        """Return organisation segments where the person is not a member."""
        segments = Segment.objects.filter(
            organisation=person.organisation, status="ACTIVE", ussd_enabled=True
        ).exclude(
            id__in=SegmentMember.objects.filter(person=person).values_list(
                "segment_id", flat=True
            )
        )
        segment_names = [segment.name for segment in segments]
        return list(segment_names)

    @staticmethod
    def add_person_to_segment(
        person: Person,
        segment_name: str,
    ) -> bool:
        """Adds a person to a segment with these details.

        Args:
            person (Person): The person instance being added to the segment.
            segment (Segment): The segement instance to which the person is being added.

        Returns:
            bool: True if the person is added successfully, False otherwise.
        """
        try:
            region = person.associated_region
            manager = SegmentManager(person)
            segment = Segment.objects.get(name=segment_name)
            segment_member = SegmentMember(
                person=person,
                segment=segment,
                source="USSD",
                member_associated_region=region,
                **manager.common_fields,
            )
            segment_member.save()
            return True
        except Exception as e:
            logger.error(f"Error adding person to segment: {e}")
            raise RuntimeError(f"Error adding person to segment: {e}")

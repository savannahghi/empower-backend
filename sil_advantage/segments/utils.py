"""Segment utils."""
import logging
from dataclasses import dataclass
from enum import Enum, unique
from typing import Dict

from django.conf import settings

from sil_advantage.common.models.common_models import Person
from sil_advantage.segments.models import (
    FilterAllowedOperations,
    Segment,
    SegmentMember,
    SegmentMemberAdditionAttributes,
)
from sil_advantage.sil_auth.models import SILUser

LOGGER = logging.getLogger(__file__)


@dataclass
class CubeConfig:
    """Class representing configuration for a cube query."""

    member: str


@unique
class CubeFilterOperations(Enum):
    """Enumeration of Cube's filter operations."""

    EQUALS = "equals"
    LESS_THAN = "lt"
    GREATER_THAN = "gt"
    GREATER_THAN_OR_EQUAL_TO = "gte"
    LESS_THAN_OR_EQUAL_TO = "lte"


CUBE_OPERATOR_MAP = {
    FilterAllowedOperations.EQUALS: CubeFilterOperations.EQUALS,
    FilterAllowedOperations.LESS_THAN: CubeFilterOperations.LESS_THAN,
    FilterAllowedOperations.GREATER_THAN: CubeFilterOperations.GREATER_THAN,
    FilterAllowedOperations.LESS_THAN_OR_EQUAL_TO: CubeFilterOperations.LESS_THAN_OR_EQUAL_TO,  # noqa: B950
    FilterAllowedOperations.GREATER_THAN_OR_EQUAL_TO: CubeFilterOperations.GREATER_THAN_OR_EQUAL_TO,  # noqa: B950
}


def build_segment_filter_cube_query(segment: Segment) -> dict:
    """Builds the CubeJS query required to execute segment filters.

    Sample query format:
        {
            "query": {
                "dimensions": ["patients_poc.person_id"],
                "total": true,
                "filters": [
                    {
                        "or": [
                        {
                            "and": [
                            {
                                "member": "patients_poc.obs_test_done_code",
                                "operator": "equals",
                                "values": [
                                "5089"
                                ]
                            }
                            ]
                        }
                        ]
                    }
                ]
            }
        }
    """
    filter_groups = segment.filter_groups.prefetch_related()
    cube_query_filter: Dict[str, list] = {"or": []}

    for filter_group in filter_groups:
        filter_group_query: Dict[str, list] = {"and": []}
        filter_values = filter_group.filters.select_related().all()

        for filter_value in filter_values:
            cube_config = CubeConfig(**filter_value.filter.cube_config)

            filter_query = {
                "member": cube_config.member,
                "operator": CUBE_OPERATOR_MAP[
                    filter_value.operation  # type:ignore
                ].value,
                "values": [filter_value.value],
            }

            filter_group_query["and"].append(filter_query)

        cube_query_filter["or"].append(filter_group_query)

    cube_query = {
        "dimensions": ["patients_poc.person_id"],
        "filters": [cube_query_filter],
        "total": True,
    }

    return cube_query


def add_cube_query_person_to_segment(person_id_list: list, segment: Segment) -> None:
    """Adds patients returned from a cube query to a segment."""
    segment_member_list = []

    admin_email = settings.SYSTEM_ADMIN_EMAIL
    system_admin = SILUser.objects.get(email=admin_email).id

    common_fields = {
        "created_by": system_admin,
        "updated_by": system_admin,
        "branch_id": segment.branch_id,
        "cluster_id": segment.cluster_id,
        "department_id": segment.department_id,
        "workstation_id": segment.workstation_id,
    }
    for person_id in person_id_list:
        try:
            person = Person.objects.get(id=person_id)
        except Person.DoesNotExist:
            error_msg = (
                f"Unable to add member to Segment. "
                f"Person matching ID {person} not found!"
            )
            LOGGER.error(error_msg)
            continue

        segment_member = SegmentMember(
            organisation=person.organisation,
            person=person,
            segment=segment,
            source=SegmentMemberAdditionAttributes.AUTOMATIC,
            **common_fields,
        )
        segment_member_list.append(segment_member)
    SegmentMember.objects.bulk_create(segment_member_list)

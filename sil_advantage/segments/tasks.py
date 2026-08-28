"""Segment tasks."""
import logging
import uuid
from uuid import UUID

from django.conf import settings

from sil_advantage.common.tasks import BaseTaskWithRetry
from sil_advantage.common.utilities.cube import CubeJS
from sil_advantage.config import celery_app
from sil_advantage.segments.models import (
    FilterExecutionStatus,
    MessageTemplate,
    Segment,
    SegmentMember,
    SegmentMemberAdditionAttributes,
    SegmentMemberStatus,
    SegmentMessage,
    SegmentMessageDelivery,
    SegmentMessageDeliveryType,
)
from sil_advantage.segments.utils import (
    add_cube_query_person_to_segment,
    build_segment_filter_cube_query,
)
from sil_advantage.sil_auth.models import SILUser

LOGGER = logging.getLogger(__file__)

logger = logging.getLogger(__name__)


@celery_app.task(base=BaseTaskWithRetry)
def send_segment_scheduled_recurrent_messages(id: str) -> None:
    """Sends a scheduled sequenced message to members of the segment.

    Args:
        id (str): The ID of the `SegmentMessage` object.
    """
    segment_message = SegmentMessage.objects.select_related().get(id=id)

    segment = segment_message.segment
    template = segment_message.template
    sender = segment_message.sender
    delivery_type = SegmentMessageDeliveryType(segment_message.delivery_type)

    for member in segment.segment_memberships.iterator():
        template.send_message(
            recipient=member,
            sender=sender,
            delivery_type=delivery_type,
            segment_message=segment_message,
        )


@celery_app.task(base=BaseTaskWithRetry)
def send_segment_scheduled_one_time_messages(id: str) -> None:
    """Sends a scheduled one time message to members of the segment.

    Args:
        id (str): The ID of the `SegmentMessage` object.
    """
    segment_message = SegmentMessage.objects.select_related().get(id=id)

    segment = segment_message.segment
    template = segment_message.template
    sender = segment_message.sender
    delivery_type = SegmentMessageDeliveryType(segment_message.delivery_type)

    for member in segment.segment_memberships.iterator():
        template.send_message(
            recipient=member,
            sender=sender,
            delivery_type=delivery_type,
            segment_message=segment_message,
        )


@celery_app.task(base=BaseTaskWithRetry)
def send_segment_instant_messages(id: str) -> None:
    """Sends an instant message to members of the segment.

    Args:
        id (str): The ID of the `SegmentMessage` object.
    """
    segment_message = SegmentMessage.objects.select_related().get(id=id)

    segment = segment_message.segment
    template = segment_message.template
    sender = segment_message.sender
    delivery_type = SegmentMessageDeliveryType(segment_message.delivery_type)

    for member in segment.segment_memberships.iterator():
        template.send_message(
            recipient=member,
            sender=sender,
            delivery_type=delivery_type,
            segment_message=segment_message,
        )


@celery_app.task()
def retry_failed_to_send_segment_messages(
    segment_message_id: UUID, message_template_id: UUID
) -> None:
    """Retries sending segment messages that failed to deliver."""
    failed_segment_messages = SegmentMessageDelivery.objects.filter(
        segment_message_id=segment_message_id,
        message_template_id=message_template_id,
        sms__state="FAILED",
    )

    segment_message = SegmentMessage.objects.get(id=segment_message_id)
    template = segment_message.template
    sender = segment_message.sender
    delivery_type = SegmentMessageDeliveryType(segment_message.delivery_type)

    for failed_segment_message in failed_segment_messages:
        template.send_message(
            recipient=failed_segment_message.member,
            sender=sender,
            delivery_type=delivery_type,
        )

        sms = failed_segment_message.sms
        sms.state = "RETRIED"  # type: ignore
        sms.save()  # type: ignore


@celery_app.task(base=BaseTaskWithRetry)
def send_segment_welcome_message(
    segment_message_id: str, segment_member_id: str
) -> None:
    """Sends a welcome message to a segment member."""
    template = MessageTemplate.objects.get(id=segment_message_id)
    intention = "DIRECT_MESSAGE"

    member = SegmentMember.objects.get(id=segment_member_id)
    template.send_message(
        recipient=member,
        delivery_type=SegmentMessageDeliveryType.INSTANT,
        intention=intention,
    )


@celery_app.task(base=BaseTaskWithRetry)
def send_segment_joining_messages(segment_member_id: str) -> None:
    """Sends a new member to a segment messages on joining a segment."""
    recipient = SegmentMember.objects.get(id=segment_member_id)

    messages = recipient.segment.segment_messages.filter(send_on_segment_join=True)
    for message in messages:
        template = message.template
        sender = message.sender
        delivery_type = SegmentMessageDeliveryType(message.delivery_type)

        template.send_message(
            recipient=recipient, sender=sender, delivery_type=delivery_type
        )


@celery_app.task()
def execute_segment_filter_cube_query(segment_id: UUID) -> None:
    """Executes a segment filter cube query.

    Cube query response format:
        "data": [
            {
                "patients_poc.person_id": "038556cc-9a03-4433-8ca6-3021f85d097e"
            },
        ]
    """
    admin_email = settings.SYSTEM_ADMIN_EMAIL
    system_admin = SILUser.objects.get(email=admin_email).id

    segment = Segment.objects.get(id=segment_id)

    segment.log_filter_execution_status_transition(FilterExecutionStatus.IN_PROGRESS)
    cube_query = build_segment_filter_cube_query(segment)
    slade_code = segment.organisation.slade_code
    try:
        cube_js = CubeJS(slade_code)

        response = cube_js.api_call(
            url=cube_js.query_base_url, payload=cube_query
        ).json()
        cube_response = response["data"]
    except Exception as e:
        logger.error(f"Error executing segment filter query: {str(e)}")
        segment.log_filter_execution_status_transition(
            FilterExecutionStatus.FAILED, reason=f"Filter execution failed: {str(e)}"
        )
        return

    existing_members = segment.segment_memberships.filter(
        source=SegmentMemberAdditionAttributes.AUTOMATIC
    )

    cube_person_id_list = [
        uuid.UUID(patient[cube_query["dimensions"][0]]) for patient in cube_response
    ]
    if not existing_members:
        add_cube_query_person_to_segment(
            person_id_list=cube_person_id_list, segment=segment
        )

        segment.log_filter_execution_status_transition(FilterExecutionStatus.SUCCESS)
        return

    existing_persons_ids = existing_members.values_list("person__id", flat=True)
    confirmed_persons_ids = existing_members.filter(
        status=SegmentMemberStatus.CONFIRMED
    ).values_list("person__id", flat=True)
    retired_persons_ids = existing_members.filter(
        status=SegmentMemberStatus.RETIRED
    ).values_list("person__id", flat=True)

    new_persons_list = list(
        set(cube_person_id_list).difference(set(existing_persons_ids))
    )

    if new_persons_list:
        add_cube_query_person_to_segment(
            person_id_list=new_persons_list, segment=segment
        )

    expelled_person_list = list(
        set(confirmed_persons_ids).difference(set(cube_person_id_list))
    )
    # retire expelled members
    if expelled_person_list:
        for expelled_person in expelled_person_list:
            member = SegmentMember.objects.get(
                person_id=expelled_person, segment=segment
            )
            member.status = SegmentMemberStatus.RETIRED
            member.transition({"updated_by": system_admin})

    confirmed_person_list = list(
        set(retired_persons_ids).intersection(set(cube_person_id_list))
    )

    # confirm retired members
    if confirmed_person_list:
        for confirmed_person in confirmed_person_list:
            member = SegmentMember.objects.get(
                person_id=confirmed_person, segment=segment
            )
            member.status = SegmentMemberStatus.CONFIRMED
            member.transition({"updated_by": system_admin})

    segment.log_filter_execution_status_transition(FilterExecutionStatus.SUCCESS)

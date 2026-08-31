"""Test segment tasks."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from model_bakery import baker

from sil_advantage.common.models import Person, PersonContact
from sil_advantage.common.utilities.cube import CubeJS
from sil_advantage.notifications.sms.models import SMS, SenderID
from sil_advantage.segments.models import (
    Filter,
    FilterAllowedOperations,
    FilterExecutionStatus,
    FilterGroup,
    FilterGroupFilter,
    FilterValueType,
    MessageTemplate,
    Segment,
    SegmentMember,
    SegmentMemberAdditionAttributes,
    SegmentMemberStatus,
    SegmentMessage,
    SegmentMessageDelivery,
    SegmentMessageDeliveryType,
    SegmentMessageStatus,
)
from sil_advantage.segments.models.constants import SegmentStatus
from sil_advantage.segments.tasks import (
    execute_segment_filter_cube_query,
    retry_failed_to_send_segment_messages,
    send_segment_instant_messages,
    send_segment_joining_messages,
    send_segment_scheduled_one_time_messages,
    send_segment_scheduled_recurrent_messages,
    send_segment_welcome_message,
)
from tests.common.utility import QuintusReponse

pytestmark = pytest.mark.django_db


@patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
def test_send_segment_scheduled_recurrent_messages_with_message(
    mock_send_sms, organisation, organisation_user
):
    """Test sending sequenced messages."""
    segment = baker.make(
        Segment, organisation=organisation, created_by=organisation_user.id
    )

    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
        message_type="SEQUENCED",
        status=SegmentMessageStatus.ACTIVE,
    )

    segment_message = baker.make(
        SegmentMessage,
        delivery_type=SegmentMessageDeliveryType.SCHEDULED_RECURRENT,
        template=message,
        segment=segment,
        created_by=organisation_user.id,
        sequence_interval="0 13 * * WED",
    )

    # no member in the segment
    send_segment_scheduled_recurrent_messages(str(segment_message.id))
    assert SegmentMessageDelivery.objects.count() == 0

    person = baker.make(
        Person, organisation=organisation, created_by=organisation_user.id
    )
    member = baker.make(
        SegmentMember,
        person=person,
        segment=segment,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    # member without contact
    send_segment_scheduled_recurrent_messages(str(segment_message.id))
    assert SegmentMessageDelivery.objects.count() == 0

    baker.make(
        PersonContact,
        person=person,
        contact_type="phone_number",
        contact="+254722000003",
    )

    # segment member first sms
    send_segment_scheduled_recurrent_messages(str(segment_message.id))
    assert SegmentMessageDelivery.objects.count() == 1

    # Fake successful delivery
    delivery_obj = SegmentMessageDelivery.objects.filter(member=member).first()
    sms = baker.make(
        SMS,
        organisation=organisation,
        # sender=sender,
        message="Hi there",
        recipients=["+254722060000"],
        intention="BROADCAST",
        state="DELIVERED",
    )

    delivery_obj.sms = sms
    delivery_obj.save()

    # repeat sms no effect i.e no next message in sequence
    send_segment_scheduled_recurrent_messages(str(segment_message.id))
    assert SegmentMessageDelivery.objects.count() == 1


@patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
def test_send_segment_scheduled_one_time_messages(
    mock_send_sms, organisation, organisation_user
):
    """Test sending sequenced one time messages."""
    segment = baker.make(
        Segment, organisation=organisation, created_by=organisation_user.id
    )

    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
        message_type="SINGULAR",
        status=SegmentMessageStatus.ACTIVE,
    )

    segment_message = baker.make(
        SegmentMessage,
        delivery_type=SegmentMessageDeliveryType.SCHEDULED_ONE_TIME,
        template=message,
        segment=segment,
        created_by=organisation_user.id,
        scheduled_at=timezone.now(),
    )

    # no member in the segment
    send_segment_scheduled_one_time_messages(str(segment_message.id))
    assert SegmentMessageDelivery.objects.count() == 0

    person = baker.make(
        Person, organisation=organisation, created_by=organisation_user.id
    )
    baker.make(
        SegmentMember,
        person=person,
        segment=segment,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    # member without contact
    send_segment_scheduled_one_time_messages(str(segment_message.id))
    assert SegmentMessageDelivery.objects.count() == 0

    baker.make(
        PersonContact,
        person=person,
        contact_type="phone_number",
        contact="+254722000002",
    )

    send_segment_scheduled_one_time_messages(str(segment_message.id))
    assert SegmentMessageDelivery.objects.count() == 1


@patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
def test_send_segment_instant_messages(mock_send_sms, organisation, organisation_user):
    """Test sending non sequenced/instant messages to a segment."""
    segment = baker.make(
        Segment, organisation=organisation, created_by=organisation_user.id
    )

    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        template="Hello World!",
        created_by=organisation_user.id,
        message_type="SINGULAR",
        status=SegmentMessageStatus.ACTIVE,
    )
    sender = baker.make(
        SenderID,
        name="BeWellApp",
        sender_type="TRANSACTION",
        start_date=timezone.now(),
        end_date=timezone.now() + timedelta(days=90),
        organisation=organisation,
        active=True,
    )
    segment_message = baker.make(
        SegmentMessage,
        delivery_type=SegmentMessageDeliveryType.SCHEDULED_ONE_TIME,
        template=message,
        segment=segment,
        sender=sender,
        created_by=organisation_user.id,
        scheduled_at=timezone.now(),
    )

    person = baker.make(
        Person,
        organisation=organisation,
        created_by=organisation_user.id,
        branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
    )
    baker.make(
        SegmentMember,
        person=person,
        segment=segment,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    # member without contact
    send_segment_instant_messages(str(segment_message.id))
    assert SegmentMessageDelivery.objects.count() == 0

    baker.make(
        PersonContact,
        person=person,
        contact_type="phone_number",
        contact="+254722000001",
    )

    send_segment_instant_messages(str(segment_message.id))
    segment_message_delivery_qs = SegmentMessageDelivery.objects.all()
    segment_message_delivery_obj = segment_message_delivery_qs.first()

    assert segment_message_delivery_qs.count() == 1

    mock_send_sms.assert_called_once_with(
        queue="advantage_tasks",
        priority=5,
        args=(
            "BROADCAST",
            "Hello World!",
            ["+254722000001"],
            organisation.slade_code,
            person.branch_id,
            None,
        ),
        kwargs={
            "sender_id": sender.id,
            "model_name": "segments.segmentmessagedelivery",
            "model_obj_pk": segment_message_delivery_obj.id,
        },
    )


@pytest.mark.usefixtures("default_transactional_sender")
@patch.object(MessageTemplate, "send_message")
def test_retry_failed_to_send_segment_messages(
    mock_send_message, organisation, organisation_user
):
    """Test retrying failed to send segment message."""
    segment = baker.make(
        Segment, organisation=organisation, created_by=organisation_user.id
    )

    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        template="Hello World!",
        created_by=organisation_user.id,
        message_type="SINGULAR",
    )
    sender = SenderID.objects.filter(name="BeWellApp").latest("created")
    segment_message = baker.make(
        SegmentMessage,
        delivery_type=SegmentMessageDeliveryType.SCHEDULED_ONE_TIME,
        template=message,
        segment=segment,
        sender=sender,
        created_by=organisation_user.id,
        scheduled_at=timezone.now(),
    )
    person = baker.make(
        Person,
        organisation=organisation,
        created_by=organisation_user.id,
        branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
    )

    member = baker.make(
        SegmentMember,
        person=person,
        segment=segment,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    sms = baker.make(
        SMS,
        organisation=organisation,
        sender=sender,
        message="Hi there",
        recipients=["+254722060000"],
        intention="BROADCAST",
        state="FAILED",
    )

    segment_message_delivery = baker.make(
        SegmentMessageDelivery,
        member=member,
        dispatched_at=timezone.now(),
        message_template=message,
        segment_message=segment_message,
        sms=sms,
    )

    retry_failed_to_send_segment_messages(
        segment_message_id=segment_message.id, message_template_id=message.id
    )
    segment_message_delivery.refresh_from_db()

    mock_send_message.assert_called_once_with(
        recipient=member,
        sender=sender,
        delivery_type=SegmentMessageDeliveryType.SCHEDULED_ONE_TIME,
    )
    assert segment_message_delivery.sms.state == "RETRIED"


def test_send_segment_welcome_message(organisation, organisation_user):
    """Test sending a segment welcome message."""
    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
        template="Welcome!",
        status=SegmentMessageStatus.ACTIVE,
    )
    segment = baker.make(
        Segment,
        organisation=organisation,
        created_by=organisation_user.id,
        welcome_message_template=message,
        send_welcome_message_notification=True,
    )
    person = baker.make(
        Person,
        first_name="Paul",
        last_name="Atreides",
        title="Duke",
        organisation=organisation,
        created_by=organisation_user.id,
        branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
    )
    baker.make(
        PersonContact,
        person=person,
        contact_type="phone_number",
        contact="+254722060000",
    )

    member = baker.make(
        SegmentMember,
        person=person,
        segment=segment,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    send_segment_welcome_message(
        segment_message_id=segment.welcome_message_template.id,
        segment_member_id=member.id,
    )
    assert SegmentMessageDelivery.objects.count() == 1


def test_send_segment_joining_messages(organisation, organisation_user):
    """Test sending a segment welcome message."""
    segment = baker.make(
        Segment,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    person = baker.make(
        Person,
        first_name="Paul",
        last_name="Atreides",
        title="Duke",
        organisation=organisation,
        created_by=organisation_user.id,
        branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
    )
    baker.make(
        PersonContact,
        person=person,
        contact_type="phone_number",
        contact="+254722060000",
    )

    member = baker.make(
        SegmentMember,
        person=person,
        segment=segment,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    message_one = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
        template="This is your first message",
        status=SegmentMessageStatus.ACTIVE,
    )

    baker.make(
        SegmentMessage,
        template=message_one,
        segment=segment,
        organisation=organisation,
        created_by=organisation_user.id,
        send_on_segment_join=True,
        delivery_type=SegmentMessageDeliveryType.INSTANT,
    )

    send_segment_joining_messages(member.id)

    assert SegmentMessageDelivery.objects.count() == 1


@patch.object(CubeJS, "api_call")
@patch.object(CubeJS, "get_access_token")
def test_execute_segment_filter_cube_query(
    mock_cube_login,
    mock_cube_api_call,
    organisation,
    organisation_user,
):
    """Test executing a segment filter cube query."""
    segment = baker.make(
        Segment,
        organisation=organisation,
        created_by=organisation_user.id,
        filter_execution_status=FilterExecutionStatus.PENDING,
    )
    filter_one = baker.make(
        Filter,
        name="Gender",
        allowed_operations=[FilterAllowedOperations.EQUALS],
        value_type=FilterValueType.CLOSE_ENDED,
        cube_config={
            "member": "patients_poc.gender",
        },
    )
    filter_group = baker.make(
        FilterGroup,
        name="Sample Filter Group",
        segment=segment,
    )
    filter_group = baker.make(
        FilterGroupFilter,
        value="MALE",
        filter=filter_one,
        filter_group=filter_group,
        operation=FilterAllowedOperations.EQUALS,
    )

    person = baker.make(
        Person,
        first_name="Paul",
        last_name="Atreides",
        title="Duke",
        organisation=organisation,
        created_by=organisation_user.id,
        branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
    )

    def mocked_cube_response(url, *args, **kwargs):
        """Mock query response from Cube."""
        data = [
            {"patients_poc.person_id": f"{person.id}"},
            {"patients_poc.person_id": "5006ae91-d8b6-4e99-9ea9-9ddb462f4721"},
        ]

        return QuintusReponse(data={"data": data})

    mock_cube_api_call.side_effect = mocked_cube_response
    execute_segment_filter_cube_query(segment.id)

    segment.refresh_from_db()
    assert segment.filter_execution_status == FilterExecutionStatus.SUCCESS

    filter_execution_logs = segment.filter_execution_logs.all()
    assert (
        filter_execution_logs.count() == 2
    )  # Two transitions: PENDING -> IN_PROGRESS -> SUCCESS
    assert filter_execution_logs.filter(
        status_from=FilterExecutionStatus.PENDING,
        status_to=FilterExecutionStatus.IN_PROGRESS,
    ).exists()
    assert filter_execution_logs.filter(
        status_from=FilterExecutionStatus.IN_PROGRESS,
        status_to=FilterExecutionStatus.SUCCESS,
    ).exists()


@patch.object(CubeJS, "api_call")
@patch.object(CubeJS, "get_access_token")
def test_execute_segment_filter_cube_query_with_existing_members(
    mock_cube_login,
    mock_cube_api_call,
    organisation,
    organisation_user,
):
    """Test executing a segment filter cube query with existing members."""
    segment = baker.make(
        Segment,
        organisation=organisation,
        created_by=organisation_user.id,
    )
    filter_one = baker.make(
        Filter,
        name="Gender",
        allowed_operations=[FilterAllowedOperations.EQUALS],
        value_type=FilterValueType.CLOSE_ENDED,
        cube_config={
            "member": "patients_poc.gender",
        },
    )
    filter_group = baker.make(
        FilterGroup,
        name="Sample Filter Group",
        segment=segment,
    )
    filter_group = baker.make(
        FilterGroupFilter,
        value="MALE",
        filter=filter_one,
        filter_group=filter_group,
        operation=FilterAllowedOperations.EQUALS,
    )
    person = baker.make(
        Person,
        first_name="Paul",
        last_name="Atreides",
        title="Duke",
        organisation=organisation,
        created_by=organisation_user.id,
        branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
    )

    person_two = baker.make(
        Person,
        first_name="Nicole",
        last_name="Ubiver",
        title="Duke",
        organisation=organisation,
        created_by=organisation_user.id,
        branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
    )

    segment_member_two = baker.make(
        SegmentMember,
        person=person_two,
        segment=segment,
        organisation=organisation,
        created_by=organisation_user.id,
        source=SegmentMemberAdditionAttributes.AUTOMATIC,
    )
    segment_member_two.status = SegmentMemberStatus.RETIRED
    segment_member_two.transition({"updated_by": organisation_user.id})

    person_three = baker.make(
        Person,
        first_name="Nicole",
        last_name="Ubiver",
        title="Duke",
        organisation=organisation,
        created_by=organisation_user.id,
        branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
    )

    baker.make(
        SegmentMember,
        person=person_three,
        segment=segment,
        organisation=organisation,
        created_by=organisation_user.id,
        source=SegmentMemberAdditionAttributes.AUTOMATIC,
    )

    def mocked_cube_response(url, *args, **kwargs):
        """Mock query response from Cube."""
        data = [
            {"patients_poc.person_id": f"{person.id}"},
            {"patients_poc.person_id": f"{person_two.id}"},
        ]

        return QuintusReponse(data={"data": data})

    mock_cube_api_call.side_effect = mocked_cube_response
    execute_segment_filter_cube_query(segment.id)

    segment.refresh_from_db()
    assert segment.filter_execution_status == FilterExecutionStatus.SUCCESS


@patch.object(CubeJS, "api_call")
@patch.object(CubeJS, "get_access_token")
def test_execute_segment_filter_cube_query_with_no_segment_actions(
    mock_cube_login,
    mock_cube_api_call,
    organisation,
    organisation_user,
):
    """Test executing a segment filter cube query with existing members."""
    segment = baker.make(
        Segment,
        organisation=organisation,
        created_by=organisation_user.id,
    )
    person = baker.make(
        Person,
        first_name="Nicole",
        last_name="Ubiver",
        title="Duke",
        organisation=organisation,
        created_by=organisation_user.id,
        branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
    )

    baker.make(
        SegmentMember,
        person=person,
        segment=segment,
        organisation=organisation,
        created_by=organisation_user.id,
        source=SegmentMemberAdditionAttributes.AUTOMATIC,
    )

    def mocked_cube_response(url, *args, **kwargs):
        """Mock query response from Cube."""
        data = [
            {"patients_poc.person_id": f"{person.id}"},
        ]
        return QuintusReponse(data={"data": data})

    mock_cube_api_call.side_effect = mocked_cube_response
    execute_segment_filter_cube_query(segment.id)

    segment.refresh_from_db()
    assert segment.filter_execution_status == FilterExecutionStatus.SUCCESS


@patch.object(CubeJS, "api_call")
@patch.object(CubeJS, "get_access_token")
def test_execute_segment_filter_cube_query_failure(
    mock_cube_login, mock_cube_api_call, organisation, organisation_user
):
    """Test handling exception during segment filter cube query execution."""
    segment = baker.make(
        Segment,
        organisation=organisation,
        created_by=organisation_user.id,
        filter_execution_status=FilterExecutionStatus.PENDING,
    )

    mock_cube_api_call.side_effect = Exception("API call failed")

    execute_segment_filter_cube_query(segment.id)

    segment.refresh_from_db()

    assert segment.filter_execution_status == FilterExecutionStatus.FAILED
    filter_execution_logs = segment.filter_execution_logs.all()
    failed_log = filter_execution_logs.get(
        status_from=FilterExecutionStatus.IN_PROGRESS,
        status_to=FilterExecutionStatus.FAILED,
    )
    assert failed_log.reason == "Filter execution failed: API call failed"


@patch.object(CubeJS, "api_call")
@patch.object(CubeJS, "get_access_token")
def test_execute_segment_filter_respect_segment_status(
    mock_cube_login, mock_cube_api_call, organisation, organisation_user
):
    """Test that segment filters respect segment status before execution."""
    segment = baker.make(
        Segment,
        organisation=organisation,
        created_by=organisation_user.id,
        filter_execution_status=FilterExecutionStatus.PENDING,
        status=SegmentStatus.RETIRED,
    )

    with pytest.raises(
        ValidationError, match="Cannot execute filters on a deactivated segment."
    ):
        execute_segment_filter_cube_query(segment.id)

    segment.refresh_from_db()
    assert segment.filter_execution_status == FilterExecutionStatus.PENDING


def test_invalid_transition():
    """Test invalid status transition in log_filter_execution_status_transition."""
    segment = baker.make(
        Segment,
        filter_execution_status=FilterExecutionStatus.SUCCESS,
    )

    with pytest.raises(
        ValidationError, match="Invalid transition from SUCCESS to PENDING."
    ):
        segment.log_filter_execution_status_transition(FilterExecutionStatus.PENDING)

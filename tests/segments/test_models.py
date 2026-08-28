"""Segment model tests."""
import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
import time_machine
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from model_bakery import baker

from sil_advantage.common.models import Person, PersonContact
from sil_advantage.common.models.common_models import Attachment
from sil_advantage.notifications.sms.models import SMS, SenderID
from sil_advantage.patients.models import PatientListUpload
from sil_advantage.segments.models import (
    Filter,
    Journey,
    MessageTemplate,
    Segment,
    SegmentLabels,
    SegmentMember,
    SegmentMemberStatus,
    SegmentMessage,
    SegmentMessageDelivery,
    SegmentMessageDeliveryType,
    SegmentMessageStatus,
    SegmentStatus,
    get_next_sequence_message,
)
from sil_advantage.segments.models.segments import SegmentUpload

pytestmark = pytest.mark.django_db


def test_validate_segment_attributes() -> None:
    """Test validate segment attributes."""
    invalid_data = {
        "name": SegmentLabels.CERVICAL_CANCER_HIGH_RISK.label,
        "label": SegmentLabels.CERVICAL_CANCER_HIGH_RISK,
        "attributes": {"demographics": "Not a valid demographic"},
    }

    with pytest.raises(ValidationError) as validation_error:
        baker.make(Segment, **invalid_data)

    assert "is not of type 'object'" in str(validation_error.value)

    valid_data = {
        "name": SegmentLabels.CERVICAL_CANCER_HIGH_RISK.label,
        "label": SegmentLabels.CERVICAL_CANCER_HIGH_RISK,
        "attributes": {"demographics": {"gender": ["MALE"]}},
    }

    segment = baker.make(Segment, **valid_data)

    assert Segment.objects.filter(id=segment.id).exists() is True


def test_validate_segment_without_attributes() -> None:
    """Test validate creating a segment without attributes."""
    valid_data = {
        "name": SegmentLabels.CERVICAL_CANCER_HIGH_RISK.label,
        "label": SegmentLabels.CERVICAL_CANCER_HIGH_RISK,
    }

    segment = baker.make(Segment, **valid_data)

    assert Segment.objects.filter(id=segment.id).exists() is True


def test_segment_member_next_message(organisation, organisation_user):
    """Test segment member next message in sequence."""
    segment = baker.make(
        Segment, organisation=organisation, created_by=organisation_user.id
    )
    person = baker.make(
        Person, organisation=organisation, created_by=organisation_user.id
    )

    membership = baker.make(
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
    )

    # Should return the first/initial message in the sequence
    msg_one = get_next_sequence_message(member=membership, segment_message=message_one)
    assert msg_one is not None
    assert msg_one.id == message_one.id

    sms_one = baker.make(
        SMS,
        organisation=organisation,
        state="DELIVERED",
        message="Hi there",
        recipients=["+254722060000"],
        intention="BROADCAST",
    )

    baker.make(
        SegmentMessageDelivery,
        member=membership,
        dispatched_at=timezone.now(),
        sequence_message=message_one,
        message_template=message_one,
        sms=sms_one,
    )

    message_two = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
        parent=message_one,
    )

    # Should return the second message in the sequence after sending the first one
    msg_two = get_next_sequence_message(member=membership, segment_message=message_one)
    assert msg_two is not None
    assert msg_two.id == message_two.id

    sms_two = baker.make(
        SMS,
        organisation=organisation,
        state="DELIVERED",
        message="Hi there",
        recipients=["+254722060000"],
        intention="BROADCAST",
    )

    baker.make(
        SegmentMessageDelivery,
        member=membership,
        dispatched_at=timezone.now(),
        sequence_message=message_one,
        message_template=message_two,
        sms=sms_two,
    )

    # Should return None since there is no third message in the sequence
    msg_three = get_next_sequence_message(
        member=membership, segment_message=message_one
    )
    assert msg_three is None


def test_validate_segment_message_delivery_type(organisation, organisation_user):
    """Test validate segment message scheduling."""
    segment = baker.make(
        Segment, organisation=organisation, created_by=organisation_user.id
    )

    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    with pytest.raises(ValidationError) as validation_error_one:
        baker.make(
            SegmentMessage,
            segment=segment,
            template=message,
            delivery_type=SegmentMessageDeliveryType.SCHEDULED_ONE_TIME,
            scheduled_at=None,
        )

    assert "requires `scheduled_at` to be provided" in str(validation_error_one.value)

    with pytest.raises(ValidationError) as validation_error_two:
        baker.make(
            SegmentMessage,
            segment=segment,
            template=message,
            delivery_type=SegmentMessageDeliveryType.SCHEDULED_RECURRENT,
            sequence_interval=None,
        )

    assert "requires `sequence_interval` to be provided" in str(
        validation_error_two.value
    )


def test_validate_sequence_interval_expression(organisation, organisation_user):
    """Test validate sequence interval cron expression."""
    segment = baker.make(
        Segment, organisation=organisation, created_by=organisation_user.id
    )

    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    with pytest.raises(ValidationError) as validation_error:
        baker.make(
            SegmentMessage,
            segment=segment,
            template=message,
            delivery_type=SegmentMessageDeliveryType.SCHEDULED_RECURRENT,
            sequence_interval="invalid!!",
        )

    assert "Invalid cron expression" in str(validation_error.value)


def test_validate_updating_segment_message_delivery_type(
    organisation, organisation_user
):
    """Test validate updating a segment message delivery type."""
    segment = baker.make(
        Segment, organisation=organisation, created_by=organisation_user.id
    )

    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    segment_message = baker.make(
        SegmentMessage,
        segment=segment,
        template=message,
        delivery_type=SegmentMessageDeliveryType.SCHEDULED_RECURRENT,
        sequence_interval="0 13 * * WED",
    )

    with pytest.raises(ValidationError) as validation_error:
        segment_message.delivery_type = SegmentMessageDeliveryType.SCHEDULED_ONE_TIME
        segment_message.scheduled_at = timezone.now()
        segment_message.save()

    assert "Cannot change delivery type" in str(validation_error.value)


def test_update_segment_message_no_effect(organisation, organisation_user):
    """Test updating segment message without affecting schedule."""
    segment = baker.make(
        Segment, organisation=organisation, created_by=organisation_user.id
    )

    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    segment_message = baker.make(
        SegmentMessage,
        segment=segment,
        template=message,
        delivery_type=SegmentMessageDeliveryType.INSTANT,
    )
    segment_message.refresh_from_db()

    assert segment_message.task is None

    # no effect update
    segment_message.delivery_type = SegmentMessageDeliveryType.INSTANT
    segment_message.save()
    segment_message.refresh_from_db()

    assert segment_message.task is None

    message_two = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    segment_message_two = baker.make(
        SegmentMessage,
        segment=segment,
        template=message_two,
        delivery_type=SegmentMessageDeliveryType.SCHEDULED_RECURRENT,
        sequence_interval="0 13 * * WED",
    )
    segment_message_two.refresh_from_db()

    assert segment_message_two.task is not None

    task = segment_message_two.task
    assert task.enabled is True

    # no effect update
    segment_message_two.sequence_interval = "0 13 * * WED"
    segment_message_two.save()
    segment_message_two.refresh_from_db()

    # task still the same
    assert segment_message_two.task.pk == task.pk


def test_update_segment_recurrent_message_periodic_task(
    organisation, organisation_user
):
    """Test updating segment message periodic task."""
    segment = baker.make(
        Segment, organisation=organisation, created_by=organisation_user.id
    )

    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    segment_message = baker.make(
        SegmentMessage,
        segment=segment,
        template=message,
        delivery_type=SegmentMessageDeliveryType.SCHEDULED_RECURRENT,
        sequence_interval="0 13 * * WED",
    )
    segment_message.refresh_from_db()

    assert segment_message.task is not None

    task = segment_message.task
    assert task.enabled is True

    # Update the sequence interval
    segment_message.sequence_interval = "0 10 * * WED"
    segment_message.save()
    segment_message.refresh_from_db()
    task.refresh_from_db()

    assert segment_message.task is not None

    task_two = segment_message.task
    # the task should be new
    assert task.pk != task_two.pk

    # initial task should be disabled
    assert task.enabled is False
    assert task_two.enabled is True


def test_update_segment_one_time_message_periodic_task(organisation, organisation_user):
    """Test updating segment message periodic task."""
    segment = baker.make(
        Segment, organisation=organisation, created_by=organisation_user.id
    )

    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    segment_message = baker.make(
        SegmentMessage,
        segment=segment,
        template=message,
        delivery_type=SegmentMessageDeliveryType.SCHEDULED_ONE_TIME,
        scheduled_at=timezone.now(),
    )
    segment_message.refresh_from_db()

    assert segment_message.task is not None

    task = segment_message.task
    assert task.enabled is True

    # Update the sequence interval
    segment_message.scheduled_at = timezone.now()
    segment_message.save()
    segment_message.refresh_from_db()
    task.refresh_from_db()

    assert segment_message.task is not None

    task_two = segment_message.task
    # the task should be new
    assert task.pk != task_two.pk

    # initial task should be disabled
    assert task.enabled is False
    assert task_two.enabled is True


def test_send_personalized_message(organisation, organisation_user):
    """Test message personalization."""
    segment = baker.make(
        Segment, organisation=organisation, created_by=organisation_user.id
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

    template = baker.make(
        MessageTemplate,
        template='Hello {{ title }} {{ first_name }} {{ last_name }}, remember: "Fear is the mind-killer." Face your fears!',  # noqa: B950
        organisation=organisation,
        created_by=organisation_user.id,
        status=SegmentMessageStatus.ACTIVE,
    )

    member = baker.make(
        SegmentMember,
        person=person,
        segment=segment,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    template.send_message(
        recipient=member, delivery_type=SegmentMessageDeliveryType.INSTANT
    )

    assert SegmentMessageDelivery.objects.filter(member=member).count() == 1

    message_delivery = SegmentMessageDelivery.objects.get(
        member=member, message_template=template
    )

    assert (
        message_delivery.message
        == 'Hello Duke Paul Atreides, remember: "Fear is the mind-killer." Face your fears!'  # noqa: B950
    )

    member.extra_data = {"film": "Dune"}
    member.save()

    # with an invalid placeholder
    template_two = baker.make(
        MessageTemplate,
        template='Hello {{ invalid }} {{ first_name }} {{ last_name }} ({{ film }}), remember: "Fear is the mind-killer." Face your fears!',  # noqa: B950
        organisation=organisation,
        branch_id=person.branch_id,
        created_by=organisation_user.id,
        status=SegmentMessageStatus.ACTIVE,
    )

    template_two.send_message(
        recipient=member, delivery_type=SegmentMessageDeliveryType.INSTANT
    )

    assert SegmentMessageDelivery.objects.filter(member=member).count() == 2

    message_delivery_two = SegmentMessageDelivery.objects.get(
        member=member, message_template=template_two
    )

    assert (
        message_delivery_two.message
        == 'Hello  Paul Atreides (Dune), remember: "Fear is the mind-killer." Face your fears!'  # noqa: B950
    )


@patch("sil_advantage.segments.tasks.send_segment_welcome_message.apply_async")
def test_send_segment_welcome_message(
    mock_send_welcome_message, organisation, organisation_user
):
    """Test sending a segment welcome message."""
    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
        template="Welcome!",
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

    segment_member = baker.make(
        SegmentMember,
        person=person,
        segment=segment,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    mock_send_welcome_message.assert_called_once_with(
        queue="advantage_tasks",
        priority=5,
        countdown=30,
        args=(segment.welcome_message_template.id, segment_member.id),
    )


@patch("sil_advantage.segments.tasks.send_segment_welcome_message.apply_async")
def test_send_message_with_send_welcome_message_disabled(
    mock_send_welcome_message, organisation, organisation_user
):
    """Test send message with send welcome message disabled."""
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

    baker.make(
        SegmentMember,
        person=person,
        segment=segment,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    mock_send_welcome_message.assert_not_called()


def test_send_translated_message(organisation, organisation_user):
    """Test message translation."""
    segment = baker.make(
        Segment, organisation=organisation, created_by=organisation_user.id
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

    template = baker.make(
        MessageTemplate,
        template='Hello {{ title }} {{ first_name }} {{ last_name }}, remember: "Fear is the mind-killer." Face your fears!',  # noqa: B950
        template_sw='Waambaje {{ title }} {{ first_name }} {{ last_name }}, kumbuka: "Hofu ni muuaji wa akili." Kabiliana na hofu yako!',  # noqa: B950
        organisation=organisation,
        created_by=organisation_user.id,
        status=SegmentMessageStatus.ACTIVE,
    )

    member = baker.make(
        SegmentMember,
        person=person,
        segment=segment,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    # Default without language selection
    template.send_message(
        recipient=member, delivery_type=SegmentMessageDeliveryType.INSTANT
    )

    assert SegmentMessageDelivery.objects.filter(member=member).count() == 1

    message_delivery = SegmentMessageDelivery.objects.get(
        member=member, message_template=template
    )

    assert (
        message_delivery.message
        == 'Hello Duke Paul Atreides, remember: "Fear is the mind-killer." Face your fears!'  # noqa: B950
    )

    # With english preference
    person.language = "en"
    person.save()

    template.send_message(
        recipient=member, delivery_type=SegmentMessageDeliveryType.INSTANT
    )

    assert SegmentMessageDelivery.objects.filter(member=member).count() == 2

    message_delivery = SegmentMessageDelivery.objects.filter(
        member=member, message_template=template
    ).latest("created")

    assert (
        message_delivery.message
        == 'Hello Duke Paul Atreides, remember: "Fear is the mind-killer." Face your fears!'  # noqa: B950
    )

    # With swahili preference
    person.language = "sw"
    person.save()

    template.send_message(
        recipient=member, delivery_type=SegmentMessageDeliveryType.INSTANT
    )

    assert SegmentMessageDelivery.objects.filter(member=member).count() == 3

    message_delivery = SegmentMessageDelivery.objects.filter(
        member=member, message_template=template
    ).latest("created")

    assert (
        message_delivery.message
        == 'Waambaje Duke Paul Atreides, kumbuka: "Hofu ni muuaji wa akili." Kabiliana na hofu yako!'  # noqa: B950
    )

    # With french preference, without existing translation
    person.language = "fr"
    person.save()

    template.send_message(
        recipient=member, delivery_type=SegmentMessageDeliveryType.INSTANT
    )

    # No new message is sent
    assert SegmentMessageDelivery.objects.filter(member=member).count() == 3


def test_validate_sequenced_message_creation(organisation, organisation_user):
    """Test creating a sequence message with multiple child messages."""
    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    message_two = baker.make(
        MessageTemplate,
        parent=message,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    assert message_two.parent == message

    # A parent cannot have multiple child messages
    with pytest.raises(ValidationError) as validation_error:
        baker.make(
            MessageTemplate,
            parent=message,
            organisation=organisation,
            created_by=organisation_user.id,
        )

    assert "Parent message has an existing sequenced message." in str(
        validation_error.value
    )


def test_send_message_with_extra_member_data(organisation, organisation_user):
    """Test sending a message with extra member data."""
    segment = baker.make(
        Segment, organisation=organisation, created_by=organisation_user.id
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
        extra_data={"clinic_name": "Nairobi", "tca_date": "12/5/2024"},
        organisation=organisation,
        created_by=organisation_user.id,
    )

    assets_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "assets")
    )
    data = File(open(assets_dir + "/Test Patient Records.xlsx", "rb"))
    file = SimpleUploadedFile(
        "Test Patient Records.xlsx",
        data.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    attachment = baker.make(
        Attachment,
        content_type=file.content_type,
        data=file,
        title=file.name,
        size=file.size,
        created_by=organisation_user.id,
        updated_by=organisation_user.id,
    )
    patient_upload = baker.make(
        PatientListUpload,
        upload_file=attachment,
        process_state="COMPLETE",
        upload_type="GENERAL",
        created_by=organisation_user.id,
        updated_by=organisation_user.id,
    )

    baker.make(
        SegmentUpload,
        organisation=organisation,
        created_by=organisation_user.id,
        file_upload=patient_upload,
        segment=segment,
        extra_headers=["clinic_name", "tca_date"],
    )

    template = baker.make(
        MessageTemplate,
        template="Hello {{ title }} {{ first_name }} {{ last_name }}, You have an appointment on {{ tca_date }} at {{ clinic_name }} Clinic",  # noqa: B950
        organisation=organisation,
        created_by=organisation_user.id,
        status=SegmentMessageStatus.ACTIVE,
    )

    template.send_message(
        recipient=member, delivery_type=SegmentMessageDeliveryType.INSTANT
    )
    message_delivery = SegmentMessageDelivery.objects.get(
        member=member, message_template=template
    )

    assert (
        message_delivery.message
        == "Hello Duke Paul Atreides, You have an appointment on 12/5/2024 at Nairobi Clinic"  # noqa: B950
    )


def test_validate_segment_active_when_adding_member(organisation, organisation_user):
    """Test validate segment status when adding members."""
    segment = baker.make(Segment)

    segment.status = SegmentStatus.RETIRED
    segment.save()

    person = baker.make(
        Person, organisation=organisation, created_by=organisation_user.id
    )

    with pytest.raises(ValidationError) as validation_error:
        baker.make(
            SegmentMember,
            person=person,
            segment=segment,
            organisation=organisation,
            created_by=organisation_user.id,
        )
    assert "Member cannot be added to a retired segment!" in str(validation_error.value)


def test_validate_segment_active_when_adding_message(organisation, organisation_user):
    """Test validate segment status when adding messages."""
    segment = baker.make(Segment)

    segment.status = SegmentStatus.RETIRED
    segment.save()

    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    with pytest.raises(ValidationError) as validation_error:
        baker.make(
            SegmentMessage,
            segment=segment,
            template=message,
            delivery_type=SegmentMessageDeliveryType.INSTANT,
        )
    assert "Message cannot be added to a retired segment!" in str(
        validation_error.value
    )


@patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
def test_send_message_with_inactive_member_or_segment(
    mock_send_sms, organisation, organisation_user
):
    """Test send message with inactive segment or member."""
    segment = baker.make(Segment)
    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
        template="Hi, welcome to this segment!",
        status=SegmentMessageStatus.ACTIVE,
    )
    person = baker.make(
        Person, organisation=organisation, created_by=organisation_user.id
    )
    baker.make(
        PersonContact,
        person=person,
        contact_type="phone_number",
        contact="+254722060000",
    )
    recipient = baker.make(
        SegmentMember,
        person=person,
        segment=segment,
        organisation=organisation,
        created_by=organisation_user.id,
    )

    message.send_message(
        recipient=recipient, delivery_type=SegmentMessageDeliveryType.INSTANT
    )
    mock_send_sms.assert_called()

    segment.status = SegmentStatus.RETIRED
    segment.save()

    # send with retired  segment
    message.send_message(
        recipient=recipient, delivery_type=SegmentMessageDeliveryType.INSTANT
    )
    mock_send_sms.reset_mock()
    mock_send_sms.assert_not_called()

    recipient.status = SegmentMemberStatus.RETIRED

    # send with retired segment and member
    message.send_message(
        recipient=recipient, delivery_type=SegmentMessageDeliveryType.INSTANT
    )
    mock_send_sms.reset_mock()
    mock_send_sms.assert_not_called()


def test_validate_filter_close_ended_choices() -> None:
    """Test validate close ended choices."""
    invalid_data = {
        "name": "Gender",
        "source": "CLINICAL",
        "allowed_operations": ["EQUALS"],
        "value_type": "CLOSE_ENDED",
        "value_data_type": "STRING",
        "choice_source": "CLOSE_ENDED_CHOICES",
        "display_type": "DROPDOWN",
        "close_ended_choices": ["MALE", "FEMALE"],
    }

    with pytest.raises(ValidationError) as validation_error:
        baker.make(Filter, **invalid_data)

    assert "is not of type 'object'" in str(validation_error.value)


def test_validate_segment_message_sender(organisation, organisation_user):
    """Test validating SenderID before saving messsage."""
    segment = baker.make(
        Segment, organisation=organisation, created_by=organisation_user.id
    )

    message = baker.make(
        MessageTemplate,
        organisation=organisation,
        created_by=organisation_user.id,
    )
    sender = baker.make(
        SenderID,
        name="23456",
        sender_type="PROMOTION",
        start_date=timezone.now(),
        end_date=timezone.now() + timedelta(days=90),
        active=True,
    )

    with time_machine.travel(datetime(year=2024, month=1, day=1, hour=19)):
        # test validation with instant
        with pytest.raises(ValidationError) as validation_error:
            baker.make(
                SegmentMessage,
                sender=sender,
                segment=segment,
                template=message,
                delivery_type=SegmentMessageDeliveryType.INSTANT,
            )

        assert "Unable to schedule message!" in str(validation_error.value)

        # test validation with scheduled_one_time
        with pytest.raises(ValidationError) as validation_error_two:
            baker.make(
                SegmentMessage,
                sender=sender,
                segment=segment,
                template=message,
                delivery_type=SegmentMessageDeliveryType.SCHEDULED_ONE_TIME,
                scheduled_at=timezone.now(),
            )

        assert "Unable to schedule message!" in str(validation_error_two.value)

        # test validation with scheduled_recurrent
        with pytest.raises(ValidationError) as validation_error_three:
            baker.make(
                SegmentMessage,
                sender=sender,
                segment=segment,
                template=message,
                delivery_type=SegmentMessageDeliveryType.SCHEDULED_RECURRENT,
                sequence_interval="0 22 * * WED",
            )

        assert "Selected SenderID is unavailable" in str(validation_error_three.value)


def test_journey_unicode(organisation):
    """Test journey unicode representation."""
    journey = baker.make(
        Journey,
        name="ANC Mothers",
        description="Journey belonging to expectant mothers",
        organisation=organisation,
    )

    expected_value = journey.name
    assert str(journey) == expected_value

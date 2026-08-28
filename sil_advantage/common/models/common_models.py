"""Common concrete models."""
import datetime
import logging
import uuid
from fractions import Fraction
from typing import Optional, Sequence, Type

import phonenumbers
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from phonenumber_field.phonenumber import to_python
from PIL import Image
from sil_cacheable.orm import CacheableManager
from sil_transitions import TransitionAndLogMixin

from sil_advantage.common.constants import (
    CONTACT_TYPES,
    COUNTRY_CODES,
    DAYS_OF_WEEK,
    GENDERS,
    ID_DOCUMENT_TYPES,
    RELATIONSHIPS,
)
from sil_advantage.common.models.base import AbstractBase
from sil_advantage.common.models.mixins import OrgUnitIdsMixin
from sil_advantage.common.utilities.misc import generate_otp
from sil_advantage.scheduling import PRACTITIONER_TYPES

LOGGER = logging.getLogger(__file__)

CONTENT_TYPES = (
    ("image/png", "PNG"),
    ("image/jpeg", "JPEG"),
    ("application/pdf", "PDF"),
    ("application/vnd.ms-excel", "xlsx"),
    ("application/msword", "doc"),
    (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
    ),
    (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ),
)

UNIT_TYPE = (("COUNTY", "COUNTY"), ("SUB_COUNTY", "SUB_COUNTY"))

IMAGE_TYPES = ["image/png", "image/jpeg"]

CONSENT_STATUS_TRANSITION_GRAPH = {
    "PENDING": ["VERIFIED", "REJECTED"],
    "VERIFIED": ["REJECTED"],
    "REJECTED": ["VERIFIED"],
}


def get_directory(
    instance: "AbstractAttachment",
    filename: str,
) -> str:
    """Determine the upload_to path for every model inheriting Attachment."""
    org = instance.organisation.organisation_name
    return "{}/{}/{}".format(
        org,
        instance.__class__.__name__.lower(),
        filename,
    )


class OperatingRegion(AbstractBase):  # type: ignore[django-manager-missing]
    """Store the operating regions."""

    name = models.CharField(max_length=100)
    unit_type = models.CharField(choices=UNIT_TYPE, max_length=255)
    country = models.CharField(
        max_length=255,
        choices=COUNTRY_CODES,
        default="KEN",
    )
    heirachy_structure = models.JSONField(default=dict, blank=True, null=True)

    class Meta(AbstractBase.Meta):
        """Set model options."""

        unique_together = (
            "name",
            "unit_type",
            "organisation",
        )


class Person(OrgUnitIdsMixin, AbstractBase):  # type: ignore[django-manager-missing]
    """A generic person record.

    Demographics and administrative information about a person independent
    of a specific health-related context
    """

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    other_names = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )
    date_of_birth = models.DateField(null=True, blank=True)
    title = models.CharField(max_length=20, null=True, blank=True)
    gender = models.CharField(
        max_length=100,
        choices=GENDERS,
        null=True,
        blank=True,
    )
    deceased = models.BooleanField(default=False, blank=True)
    related_persons = models.ManyToManyField(
        "self",
        through="RelatedPerson",
        through_fields=("me", "related"),
    )
    language = models.CharField(
        max_length=4,
        choices=settings.LANGUAGES,
        null=True,
        blank=True,
    )
    # Store metadata
    metadata = models.JSONField(default=dict, null=True, blank=True)
    associated_region = models.ForeignKey(
        OperatingRegion,
        related_name="operating_region",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    model_validators = ["validate_dob"]

    objects: models.Manager["Person"] = CacheableManager()

    class Meta(AbstractBase.Meta):
        """Set model options."""

        pass

    @cached_property
    def phone_number(self) -> Optional[str]:
        """Return the persons first registered phone number.

        Prioritizes the primary contact first. Else
        return the first contact returned from the
        queryset.
        """
        contact = (
            self.person_contacts.filter(
                contact_type="phone_number",
            )
            .order_by("-is_primary_contact")
            .first()
        )
        if contact is None:
            return None
        return contact.contact

    @cached_property
    def email(self) -> Optional[str]:
        """Return the person's first registered email address."""
        try:
            return (
                self.person_contacts.filter(contact_type="email")
                .order_by("created")[0]
                .contact
            )
        except (PersonContact.DoesNotExist, IndexError):
            return None

    def get_full_name(self) -> str:
        """Return the identifying fullname for this person."""
        if self.other_names:
            return " ".join([self.first_name, self.other_names, self.last_name])
        else:
            return " ".join([self.first_name, self.last_name])

    @cached_property
    def age(self) -> Optional[dict[str, int]]:
        """Get age in years, months, weeks, and days.

        The smaller time units only contain the remainders.
        """
        dob = self.date_of_birth
        if not dob:
            return None

        today = timezone.now().date()
        age = relativedelta(today, dob)
        return {
            "years": age.years,
            "months": age.months,
            "weeks": age.weeks,
            "days": age.days % 7,
        }

    @cached_property
    def global_health_id(self) -> str | None:
        """Get the health ID for a person."""
        if not hasattr(self, "patient_person"):
            return None

        return self.patient_person.global_health_id

    @cached_property
    def sms_consent_status(self) -> str | None:
        """Returns a person's SMS communication consent status."""
        consent_qs = self.person_consents.filter(
            consent_type=ConsentType.SMS_COMMUNICATION
        )

        if consent_qs.exists():
            return consent_qs.first().status  # type: ignore
        return None

    def validate_dob(self) -> None:
        """Check that the DOB is less than today and less than 150 years."""
        if self.date_of_birth:
            errs = []
            max_age = 365 * 150
            if self.date_of_birth > timezone.now().date():
                errs.append(
                    ValidationError(
                        {"date_of_birth": _("Date of birth cannot be a future date")}
                    )
                )

            delta = datetime.timedelta(days=max_age)
            oldest_person = timezone.now().date() - delta
            if self.date_of_birth < oldest_person:
                errs.append(
                    ValidationError(
                        {
                            "date_of_birth": _(
                                "A person cannot be more than 150 years old."
                            )
                        }
                    )
                )

            if errs:
                # Ignored to first finalize cleanup
                raise ValidationError(errs)

    def __str__(self) -> str:
        """Represent a person by their full name."""
        return self.get_full_name()


class RelatedPerson(OrgUnitIdsMixin, AbstractBase):  # type: ignore[django-manager-missing]
    """FHIR related person.

    Relationships are type "N": Next-of-Kin
        http://terminology.hl7.org/CodeSystem/v2-0131
    """

    me = models.ForeignKey(
        Person,
        related_name="me",
        on_delete=models.PROTECT,
    )
    related = models.ForeignKey(
        Person,
        related_name="related",
        on_delete=models.PROTECT,
    )
    relationship = models.CharField(
        choices=RELATIONSHIPS,
        max_length=16,
    )

    objects: models.Manager["RelatedPerson"] = CacheableManager()

    class Meta(AbstractBase.Meta):
        """Set model options."""

        unique_together = (
            "me",
            "related",
        )


class AbstractAttachment(OrgUnitIdsMixin, AbstractBase):
    """Shared base model for all attachments."""

    content_type = models.CharField(
        max_length=100,
        choices=CONTENT_TYPES,
    )
    data = models.FileField(upload_to=get_directory, max_length=255)
    title = models.CharField(max_length=255)
    creation_date = models.DateTimeField(default=timezone.now)
    size = models.IntegerField(help_text="The size of the attachment in bytes")
    description = models.TextField(null=True, blank=True)
    aspect_ratio = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )
    file_hash = models.CharField(
        max_length=64,
        null=True,
        blank=True,
    )
    metadata = models.JSONField(default=dict, blank=True)

    model_validators: Sequence[str] = ["validate_image_size"]

    def validate_image_size(self) -> None:
        """Ensure that the supplied image size matches the actual file."""
        try:
            if self.content_type not in IMAGE_TYPES:
                return None

            image = Image.open(self.data)
            width, height = image.size
            msg_template = _(
                "Your image has a {axis} of {actual_size} {extra_text} "
                "pixels which is larger than allowable dimension of "
                "{expected_size} pixels."
            )
            msg = None
            if height > settings.MAX_IMAGE_HEIGHT:
                msg = msg_template.format(
                    axis="height",
                    actual_size=height,
                    expected_size=settings.MAX_IMAGE_HEIGHT,
                    extra_text="{extra_text}",
                )

            if width > settings.MAX_IMAGE_WIDTH:
                extra_text = _("and width of {}".format(width))
                msg = (
                    msg.format(extra_text=extra_text)
                    if msg
                    else msg_template.format(
                        axis="width",
                        actual_size=width,
                        expected_size=settings.MAX_IMAGE_WIDTH,
                        extra_text="",
                    )
                )

            if msg:
                msg = msg.format(extra_text="")
                raise ValidationError(msg)

            # Set the image aspect ratio
            float_ratio = float(width / height)
            fraction_ratio = str(Fraction(float_ratio).limit_denominator())
            self.aspect_ratio = fraction_ratio.replace("/", ":")
        except (OSError, TypeError, ValueError) as e:
            LOGGER.exception("{} - {}".format(self.__class__.__name__, e))

    class Meta:
        """Declare Attachment as an abstract model."""

        ordering = ("-updated", "-created")
        abstract = True

    def __str__(self) -> str:
        """Represent an attachment by its title."""
        return self.title


class Attachment(AbstractAttachment):
    """Shared reusable model for attachments."""


class PersonID(OrgUnitIdsMixin, AbstractBase):
    """Stored identification information about a person.

    Identification documents can be National ID card, Military IDS etc
    """

    person = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="person_ids"
    )
    id_document_type = models.CharField(
        max_length=255,
        choices=ID_DOCUMENT_TYPES,
    )
    id_value = models.CharField(max_length=60)

    organisation_verify = ["person"]

    objects: models.Manager["PersonID"] = CacheableManager()

    class Meta:
        """Make ID value unique per ID document type and person."""

        ordering = ("-updated", "-created")
        unique_together = ("id_value", "id_document_type", "person")

    def __str__(self) -> str:
        """Represent a person ID using the ID type and value."""
        return " ".join([self.id_document_type, self.id_value])


class OTPVerificationStatus(models.TextChoices):
    """Available OTP verification status."""

    PENDING = "PENDING", _("Pending")
    VERIFIED = "VERIFIED", _("Verified")


class PersonOTP(OrgUnitIdsMixin, AbstractBase):
    """Stores OTPs for a person."""

    person = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="person_otps"
    )
    code = models.CharField(max_length=8, db_index=True, default=generate_otp)
    verification_status = models.CharField(
        max_length=16,
        choices=OTPVerificationStatus.choices,
        default=OTPVerificationStatus.PENDING,
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.IntegerField(default=0)

    class Meta:
        """Set model options."""

        ordering = ("-updated", "-created")

    def verify_otp_code(self, code: str) -> bool:
        """Verifies an OTP code is valid."""
        if self.verification_status == OTPVerificationStatus.VERIFIED:
            raise ValidationError({"is_used": "OTP code has already been used"})

        if self.expires_at is not None and self.expires_at < timezone.now():
            raise ValidationError({"expires_at": "OTP code has expired"})

        if self.code != code:
            raise ValidationError({"code": "OTP code is not valid."})

        self.verification_status = OTPVerificationStatus.VERIFIED
        self.save()

        return True


class PersonAttachment(AbstractAttachment):
    """Attach files to a person e.g ID scans."""

    person = models.ForeignKey(Person, on_delete=models.PROTECT)

    organisation_verify = ["person"]


class AbstractContact(OrgUnitIdsMixin, AbstractBase):
    """Abstract Contact Model."""

    contact_type = models.CharField(
        max_length=255,
        choices=CONTACT_TYPES,
    )
    contact = models.CharField(max_length=50, null=True, blank=True)
    verified = models.BooleanField(default=False)
    consent_to_contact_given = models.BooleanField(default=True)
    is_primary_contact = models.BooleanField(default=False)

    model_validators = [
        "validate_phone_number_is_valid",
        "validate_email_address",
    ]

    class Meta:
        """Make Contact an abstract model."""

        ordering = ("-updated", "-created")
        abstract = True

    @property
    def is_phone_number(self) -> bool:
        """Return True if a contact is a phone number."""
        return self.contact_type == "phone_number"

    @property
    def is_email_address(self) -> bool:
        """Return True if a contact is an email address."""
        return self.contact_type == "email"

    def validate_phone_number_is_valid(self) -> None:
        """Ensure that only valid phone numbers are saved."""
        if self.contact:
            error_msg = {"contact": _("Enter a valid phone number.")}
            phone = to_python(self.contact)
            if not phonenumbers.is_valid_number(phone) and self.is_phone_number:
                LOGGER.error(
                    "Invalid phone number: {} -> {}".format(
                        self.contact,
                        phone,
                    )
                )
                raise ValidationError(error_msg)

    def validate_email_address(self) -> None:
        """Email address should be in the form address@domain.top_level."""
        if self.contact and self.is_email_address:
            try:
                validate_email(self.contact)
            except ValidationError as e:
                raise ValidationError({"contact": _(str(e))})


class PersonContact(AbstractContact):
    """Contact details about a person."""

    person = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="person_contacts",
    )

    organisation_verify = ["person"]

    objects: models.Manager["PersonContact"] = CacheableManager()

    def __str__(self) -> str:
        """Represent a person contact by the person's name and the contact."""
        contact = self.contact if self.contact is not None else ""
        return " ".join((self.person.get_full_name(), contact))


class UserProfile(AbstractBase):
    """This model joins a user to a person and an organisation."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="userprofile",
    )
    person = models.ForeignKey(Person, on_delete=models.PROTECT)

    def __str__(self) -> str:
        """Represent a user profile using the user and organisation."""
        return "{} : {}".format(self.user, self.organisation)


class AbstractTiming(OrgUnitIdsMixin, AbstractBase):
    """Describes the occurrence of an event that may occur multiple times.

    Reference: https://hl7.org/fhir/2020Feb/datatypes.html#Timing
    """

    day_of_week = models.CharField(max_length=1, choices=DAYS_OF_WEEK)
    start = models.TimeField()
    end = models.TimeField()

    model_validators = ["validate_start_is_before_end"]

    class Meta:
        """Make the AbstractTiming model abstract."""

        ordering = ("-updated", "-created")
        abstract = True

    def validate_start_is_before_end(self) -> None:
        """Ensure that the timing start is before its end."""
        error_msg = {"end": (_("The timing end must be greater " "than its start."))}
        if self.end < self.start:
            raise ValidationError(error_msg)


class InstanceHistory(AbstractBase):
    """Track the history of certain fields on any model."""

    model_name = models.CharField(max_length=64, db_index=True)
    instance_id = models.UUIDField(db_index=True)
    snapshot = models.JSONField()

    @classmethod
    def as_of(
        cls,
        model: Type[models.Model],
        instance_id: uuid.UUID,
        timestamp: datetime.datetime,
    ) -> Optional[dict]:
        """Return the snapshot of `instance_id` as of `timestamp`."""
        model_name = f"{model._meta.app_label}.{model._meta.model_name}"

        instance: Optional[dict] = None
        try:
            instance = (
                InstanceHistory.objects.filter(
                    model_name=model_name,
                    instance_id=instance_id,
                    created__lte=timestamp,
                )
                .latest("created")
                .snapshot
            )
        except InstanceHistory.DoesNotExist:
            pass

        return instance


class Practitioner(  # type: ignore[django-manager-missing]
    AbstractBase, OrgUnitIdsMixin
):
    """This model represents a health practitioner's profile."""

    person = models.OneToOneField(
        Person,
        on_delete=models.PROTECT,
        related_name="practitioner_person",
    )
    qualification = models.CharField(
        max_length=255,
        choices=PRACTITIONER_TYPES,
    )

    def __str__(self) -> str:
        """Represent a practitioner using their title and names."""
        return "{} {}".format(self.person.title, self.person.get_full_name())


class ConsentType(models.TextChoices):
    """Available Consent types."""

    SMS_COMMUNICATION = "SMS_COMMUNICATION", _("SMS Communication")
    SMS_HEALTH_EDUCATION = "SMS_HEALTH_EDUCATION", _("SMS Health Education")
    EMAIL_HEALTH_EDUCATION = "EMAIL_HEALTH_EDUCATION", _("Email Health Education")


class ConsentStatus(models.TextChoices):
    """Available Consent status."""

    PENDING = "PENDING", _("Pending")
    VERIFIED = "VERIFIED", _("Verified")
    REJECTED = "REJECTED", _("Rejected")


class ConsentVerificationType(models.TextChoices):
    """Available Consent status."""

    OTP = "OTP", _("OTP")
    HUMAN = "HUMAN", _("Human")
    USSD = "USSD", _("USSD")


class ConsentTransitionLog(AbstractBase):
    """Tracks changes to consent for tracking purposes."""

    consent = models.ForeignKey(
        "Consent", on_delete=models.PROTECT, related_name="consent_logs"
    )
    status_to = models.CharField(max_length=16)
    status_from = models.CharField(max_length=16)


class Consent(TransitionAndLogMixin, OrgUnitIdsMixin, AbstractBase):
    """Stores consent for a person."""

    person = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="person_consents"
    )

    consent_type = models.CharField(
        max_length=120,
        choices=ConsentType.choices,
    )
    status = models.CharField(
        max_length=16,
        choices=ConsentStatus.choices,
        default=ConsentStatus.PENDING,
    )
    verification_type = models.CharField(
        max_length=16,
        choices=ConsentVerificationType.choices,
    )

    effective_from = models.DateTimeField(null=True, blank=True, default=timezone.now)
    effective_to = models.DateTimeField(null=True, blank=True)

    # reference to the otp used for verification
    otp = models.ForeignKey(
        PersonOTP,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="consent_otps",
    )

    _transition_field = "status"
    _transition_log_model_fk_field = "consent"
    _transition_log_model = ConsentTransitionLog
    _transition_graph = CONSENT_STATUS_TRANSITION_GRAPH

    class Meta:
        """Consent meta class."""

        ordering = ("-updated", "-created")
        unique_together = ("person", "consent_type")

    def transition_log_data(self) -> dict:
        """Prepare a transition log data dict that is ready to be saved."""
        data = super().transition_log_data()
        data.update(
            {
                "created_by": self.updated_by,
                "updated_by": self.updated_by,
                "organisation": self.organisation,
            }
        )
        return data

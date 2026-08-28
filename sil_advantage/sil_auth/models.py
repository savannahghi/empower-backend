"""Authentication models."""
import logging
import uuid
from typing import Any, Optional, cast

import pyotp
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.functional import cached_property

from sil_advantage.common.cache import cached
from sil_advantage.common.models import OwnerlessAbstractBase, PersonOTP
from sil_advantage.notifications.email import send_email

LOGGER = logging.getLogger(__file__)


def send_email_on_signup(
    user: dict[str, str],
    client_url: str,
    password: Optional[str] = None,
) -> None:
    """Send user emails on successful signup."""
    plain_text = "registration/account_registration_success.txt"
    html_temp = "registration/account_registration_success.html"
    org_name = user["organisation_name"]
    context = {
        "email": user["email"],
        "organisation_name": user["organisation_name"],
        "password": password,
        "first_name": user["first_name"],
        "frontend_url": client_url,
    }
    subject = "Account Successfully Created"

    send_email(
        subject,
        [user["email"]],
        html_temp,
        plain_text,
        context,
        org_name,
    )


class SILUserManager(BaseUserManager):
    """A custom user manager."""

    def create_user(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        **extra_fields: Any,
    ) -> "SILUser":
        """Create and save a User with the given email, password."""
        if not email:
            raise ValueError("Users must have an email address")

        user = cast(
            "SILUser",
            self.model(
                email=self.normalize_email(email),
                **extra_fields,
            ),
        )
        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        **extra_fields: Any,
    ) -> "SILUser":
        """Create and save a User with the given email, DOB and password."""
        user = self.create_user(
            email=email,
            password=password,
            **extra_fields,
        )
        user.is_admin = True
        user.save(using=self._db)
        return user

    def get_queryset(self) -> models.QuerySet:
        """Limit to active users."""
        return super().get_queryset().filter(active=True)


class SILUser(AbstractBaseUser):
    """A custom user model."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    email = models.EmailField(
        verbose_name="email address",
        max_length=255,
        unique=True,
    )
    guid = models.UUIDField(unique=True, db_index=True)
    is_network_admin = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    permissions = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    business_partner = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    # Matrix
    matrix_user_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    objects = SILUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["guid"]

    organisation_verify = ["person"]

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Send user emails in the course of saving/updating user."""
        send_update_email = False
        self.full_clean(exclude=None)
        try:
            original = self.__class__.objects.get(pk=self.pk)
            if original.email != self.email:
                send_update_email = True
        except self.__class__.DoesNotExist:
            pass
        super().save(*args, **kwargs)
        if send_update_email:
            self.inform_email_change(original.email, self.email)

    class Meta:
        """User model options."""

        ordering = ("-updated", "-created")

    @cached_property
    @cached(key_attr="guid", cache_falsy=False)
    def profile(self):  # type: ignore  # circular dependency issues
        """Retrieve the user's profile instance."""
        # import's here due to circular dependency issues
        from sil_advantage.common.models import UserProfile

        try:
            return UserProfile.objects.select_related(
                "person",
                "organisation",
            ).get(user=self, active=True)
        except UserProfile.DoesNotExist:
            return False

    @cached_property
    def person(self):  # type: ignore  # circular dependency issues
        """Get the ``Person`` the user is linked to, IF ANY."""
        return self.profile.person if self.profile else None

    @cached_property
    def organisation(self):  # type: ignore  # circular dependency issues
        """Retrieve the organisation that the user belongs to."""
        return self.profile.organisation if self.profile else None

    @cached_property
    def full_name(self) -> Optional[str]:
        """Return the user's full name as a property."""
        return self.get_full_name()

    def get_full_name(self) -> Optional[str]:
        """Return the identifying fullname for this User."""
        return (
            self.person.first_name + " " + self.person.last_name
            if self.profile
            else None
        )

    def inform_email_change(
        self,
        old_email: str,
        new_email: str,
    ) -> None:
        """Inform the user that their email has been updated."""
        user_insta = {
            "organisation_name": str(self.organisation.organisation_name),
            "new_email": new_email,
            "old_email": old_email,
            "first_name": self.person.first_name,
        }
        new_email = user_insta["new_email"]
        old_email = user_insta["old_email"]
        org_name = user_insta["organisation_name"]
        subject = "Your Account information has been updated"
        plain_text_old = "registration/old_email.txt"
        html_temp_old = "registration/old_email.html"

        send_email(
            subject,
            [old_email],
            html_temp_old,
            plain_text_old,
            user_insta,
            org_name,
        )

        plain_text_new = "registration/new_email.txt"
        html_temp_new = "registration/new_email.html"
        send_email(
            subject,
            [new_email],
            html_temp_new,
            plain_text_new,
            user_insta,
            org_name,
        )

    def __str__(self) -> str:
        """Represent a user using their email."""
        return self.email

    def has_permissions(self, permissions: list[str]) -> bool:
        """Check if a user has permissions from a supplied list."""
        permission_strings = self.permissions.split(",")
        return set(permissions).intersection(set(permission_strings)) == set(
            permissions
        )

    def email_account_details(self, password: str, client_url: str) -> None:
        """Email a user details about their account when creating a new one."""
        user_insta = {
            "id": str(self.id),
            "organisation_id": str(self.organisation.id),
            "organisation_name": str(self.organisation.organisation_name),
            "email": self.email,
            "first_name": self.person.first_name,
        }
        send_email_on_signup(user_insta, client_url, password)

    @cached_property
    def user_mfa_methods(self):  # type: ignore
        """Returns enrolled MFA methods for a user."""
        return self.mfa_methods.all()


class MFAType(models.TextChoices):
    """Available MFA Types."""

    PHONE_OTP = "PHONE_OTP", "Phone OTP"
    TOTP = "TOTP", "Time-Based OTP"


class MFAStatus(models.TextChoices):
    """Status of the user MFA."""

    PENDING = "PENDING", "Pending"
    ENABLED = "ENABLED", "Enabled"
    DISABLED = "DISABLED", "Disabled"


class SILUserMFA(OwnerlessAbstractBase):
    """Keeps track of a user’s MFA."""

    user = models.ForeignKey(
        SILUser, on_delete=models.PROTECT, related_name="mfa_methods"
    )
    mfa_type = models.CharField(choices=MFAType.choices, max_length=16)
    status = models.CharField(
        choices=MFAStatus.choices, default=MFAStatus.PENDING, max_length=16
    )

    # phone OTPs
    otp = models.ForeignKey(
        PersonOTP, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    # TOTPs
    secret_key = models.CharField(
        max_length=48,
        null=True,
        blank=True,
        help_text="""
        A unique token essential for implementing two-factor authentication
        using authenticator apps.
        """,
    )

    model_validators = ["validate_phone_number_exists"]

    def validate_phone_number_exists(self) -> None:
        """Validates a user has a phone number when adding PHONE_OTP MFA."""
        if self.mfa_type == MFAType.PHONE_OTP and self.user.person.phone_number is None:
            raise ValidationError(
                {"phone number": "A phone number is required to add this MFA."}
            )

    @cached_property
    def totp_provisioning_uri(self) -> str | None:
        """Returns the provisioning URI for the OTP.

        This can then be encoded in a QR Code and used to provision an OTP app like
        Google Authenticator.
        """
        if self.secret_key is None:
            return None

        return pyotp.totp.TOTP(self.secret_key).provisioning_uri(
            name=self.user.email, issuer_name="Slade 360"
        )

    def _generate_totp_secret_key(self) -> str:
        """Generates a TOTP secret key for this user."""
        return pyotp.random_base32()

    def verify_totp_otp(self, code: str) -> bool:
        """Verify if a TOTP OTP is valid."""
        valid = pyotp.totp.TOTP(self.secret_key).verify(code)  # type: ignore
        if not valid:
            raise ValidationError({"code": "OTP code is not valid."})

        return True

    def verify_otp_code(self, code: str) -> bool:
        """Verify if the provided OTP code is valid."""
        if self.mfa_type == MFAType.PHONE_OTP and self.otp:
            return self.otp.verify_otp_code(code)
        elif self.mfa_type == MFAType.TOTP:
            return self.verify_totp_otp(code)
        else:
            return False

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Override the save method."""
        self.full_clean()

        if self._state.adding and self.mfa_type == MFAType.TOTP:
            self.secret_key = self._generate_totp_secret_key()

        super().save(*args, **kwargs)

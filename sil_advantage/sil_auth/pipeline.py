"""Functions to be added to python-social-auth to support get_user_model()."""
from typing import Any, Optional
from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions
from rest_framework.serializers import ValidationError
from social_django.models import UserSocialAuth

from sil_advantage.common.models import Organisation, Person, UserProfile
from sil_advantage.sil_auth.models import SILUser


def create_person(
    user: SILUser,
    social: UserSocialAuth,
    is_new: bool,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Person]:
    """Add to the python-social-auth pipeline to create a `Person`."""
    key = f"user_update_lock_{user.id}"
    lock_exists = cache.get(key, None) is not None
    if not is_new and lock_exists:
        # Prevent this from running in EVERY API call
        # to reduce latency which has been in the pits :(.
        return {"person": user.person}

    extra_data = social.extra_data
    first_name = extra_data.get("first_name")
    last_name = extra_data.get("last_name")
    slade_code = extra_data.get("business_partner")

    try:
        organisation = Organisation.objects.get(slade_code=slade_code)
    except BaseException:
        # roll-back models that have already been created
        social.delete()
        user.delete()
        raise ValidationError(
            {"organisation": _("This field is required to create a user.")}
        )

    if not organisation.active:
        raise exceptions.PermissionDenied("Inactive Organisation")

    if not user.person:
        person = Person.objects.create(
            first_name=first_name,
            last_name=last_name,
            organisation=organisation,
            created_by=user.pk,
            updated_by=user.pk,
        )
    else:
        person = user.person
        person.first_name = first_name
        person.last_name = last_name
        person.save(update_fields=["first_name", "last_name"])
    cache.set(key, True, 60 * 60 * 24 * 7)  # 1 week
    return {"person": person}


def create_user_profile(
    user: SILUser,
    person: Person,
    is_new: bool,
    *args: Any,
    **kwargs: Any,
) -> dict:
    """Add to the python-social-auth pipeline to create a `UserProfile`."""
    if not is_new:
        # Prevent this from running in EVERY API call
        # to reduce latency which has been in the pits :(.
        return {}

    organisation = person.organisation

    user_profile = UserProfile.objects.get_or_create(
        person=person,
        user=user,
        organisation=organisation,
        defaults={"created_by": user.pk, "updated_by": user.pk},
    )

    return {"user_profile": user_profile[0]}


def fetch_user(
    uid: UUID,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Optional[SILUser]]:
    """Try to fetch a user based on the unique_identifier field."""
    try:
        user = get_user_model().objects.get(guid=uid)
    except get_user_model().DoesNotExist:
        user = None
    return {"user": user}


def convert_permissions_to_string(
    details: dict[str, Any], *args: Any, **kwargs: Any
) -> dict[str, Any]:
    """Convert permissions from a list to a comma separated list."""
    if details.get("permissions"):
        details["permissions"] = ",".join(details["permissions"])
    return {"details": details}

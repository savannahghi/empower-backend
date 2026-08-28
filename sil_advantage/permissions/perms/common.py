"""Common permissions."""
from sil_auth_backends.utilities.utilities import PERM_NODE

# Organisations

ORGANISATION_VIEW = PERM_NODE(
    "advantage.organisation_list",
    "View organisations",
)

ORGANISATION_CREATE = PERM_NODE(
    "advantage.organisation_create",
    "Create organisations",
    is_deprecated=False,
    is_network_level=True,
)

ORGANISATION_EDIT = PERM_NODE(
    "advantage.organisation_edit",
    "Edit organisations",
    is_deprecated=False,
    is_network_level=True,
)

ORGANISATION_DELETE = PERM_NODE(
    "advantage.organisation_delete",
    "Remove organisations",
    is_deprecated=False,
    is_network_level=True,
)


# Persons

PERSON_VIEW = PERM_NODE(
    "advantage.person_list",
    "View persons",
    is_system_level=True,
)

PERSON_CREATE = PERM_NODE(
    "advantage.person_create",
    "Create persons",
    is_system_level=True,
)

PERSON_EDIT = PERM_NODE(
    "advantage.person_edit",
    "Edit persons",
    is_system_level=True,
)

PERSON_DELETE = PERM_NODE(
    "advantage.person_delete",
    "Remove persons",
    is_system_level=True,
)


# User Profiles

USER_PROFILE_VIEW = PERM_NODE(
    "advantage.user_profile_view",
    "View user profile",
    is_system_level=True,
)
USER_PROFILE_CREATE = PERM_NODE(
    "advantage.user_profile_create",
    "Create user profile",
    is_system_level=True,
)
USER_PROFILE_EDIT = PERM_NODE(
    "advantage.user_profile_edit",
    "Edit user profile",
    is_system_level=True,
)
USER_PROFILE_DELETE = PERM_NODE(
    "advantage.user_profile_delete",
    "Delete user profile",
    is_system_level=True,
)


# Operating Region

OPERATING_REGION_VIEW = PERM_NODE(
    "advantage.operating_region_view",
    "View operating region",
)

OPERATING_REGION_CREATE = PERM_NODE(
    "advantage.operating_region_create",
    "Create operating region",
)

OPERATING_REGION_EDIT = PERM_NODE(
    "advantage.operating_region_edit",
    "Edit operating region",
)

OPERATING_REGION_DELETE = PERM_NODE(
    "advantage.operating_region_delete",
    "Delete operating region",
)

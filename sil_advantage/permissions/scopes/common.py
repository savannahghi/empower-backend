"""Common scopes."""
from sil_auth_backends.utilities.utilities import SCOPE_NODE

# Organisations

ORGANISATION_READ = SCOPE_NODE(
    "advantage.organisation.read",
    "View organisations",
)
ORGANISATION_WRITE = SCOPE_NODE(
    "advantage.organisation.write",
    "Edit organisations",
)


# Persons

PERSON_READ = SCOPE_NODE(
    "advantage.person.read",
    "View persons",
)
PERSON_WRITE = SCOPE_NODE(
    "advantage.person.write",
    "Edit persons",
)


# User Profiles

USER_PROFILE_READ = SCOPE_NODE(
    "advantage.user_profile.read",
    "View user profiles",
)
USER_PROFILE_WRITE = SCOPE_NODE(
    "advantage.user_profile.write",
    "Edit user profiles",
)


# Operating Region

OPERATING_REGION_READ = SCOPE_NODE(
    "advantage.operating_region.read",
    "View operating regions",
)
OPERATING_REGION_WRITE = SCOPE_NODE(
    "advantage.operating_region.write",
    "Edit operating regions",
)

"""Common types."""
from rest_framework.request import Request

from sil_advantage.sil_auth.models import SILUser


class AuthenticatedRequest(Request):
    """Type for an authenticated Request."""

    user: SILUser

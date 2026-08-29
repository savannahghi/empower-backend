"""Keycloak bearer token authentication."""
from typing import Any, Optional

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from rest_framework import authentication, exceptions

from sil_advantage.common.models import Organisation, Person, UserProfile
from sil_advantage.sil_auth.models import SILUser

# Cache introspection so a burst of requests costs one round trip, not one each.
INTROSPECTION_CACHE_TTL = 60


class KeycloakAuthentication(authentication.BaseAuthentication):
    """Authenticate a bearer token against Keycloak, mapping it to a SILUser."""

    keyword = "Bearer"

    def authenticate(self, request: Any) -> Optional[tuple[SILUser, str]]:
        """Return the token's user, or None to fall through to the next class."""
        token = self._read_token(request)
        if token is None:
            return None

        claims = self._introspect(token)

        return self._resolve_user(claims), token

    def authenticate_header(self, request: Any) -> str:
        """Return the WWW-Authenticate challenge."""
        return self.keyword

    def _read_token(self, request: Any) -> Optional[str]:
        header = authentication.get_authorization_header(request).split()

        if not header or header[0].lower() != self.keyword.lower().encode():
            return None

        if len(header) != 2:
            raise exceptions.AuthenticationFailed(
                "Invalid Authorization header. Expected 'Bearer <token>'."
            )

        return header[1].decode()

    def _introspect(self, token: str) -> dict[str, Any]:
        cache_key = f"keycloak_introspection_{hash(token)}"

        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            response = requests.post(
                settings.KEYCLOAK["INTROSPECTION_URL"],
                data={"token": token},
                auth=(
                    settings.KEYCLOAK["CLIENT_ID"],
                    settings.KEYCLOAK["CLIENT_SECRET"],
                ),
                timeout=settings.KEYCLOAK["TIMEOUT"],
            )
            response.raise_for_status()
            claims = response.json()
        except requests.RequestException as error:
            raise exceptions.AuthenticationFailed(
                f"Could not reach Keycloak: {error}"
            ) from error

        if not claims.get("active"):
            raise exceptions.AuthenticationFailed("Token is not active.")

        cache.set(cache_key, claims, INTROSPECTION_CACHE_TTL)

        return claims

    def _resolve_user(self, claims: dict[str, Any]) -> SILUser:
        subject = claims.get("sub")
        email = claims.get("email")

        if not subject or not email:
            raise exceptions.AuthenticationFailed(
                "Token is missing the `sub` or `email` claim."
            )

        organisation = self._resolve_organisation(claims)
        permissions = ",".join(claims.get("realm_access", {}).get("roles", []))

        with transaction.atomic():
            user = SILUser.objects.filter(guid=subject).first()

            if user is None:
                user = SILUser(
                    guid=subject, email=email, permissions=permissions
                )
                # Keycloak holds the credential, and full_clean rejects a blank
                # password.
                user.set_unusable_password()
                user.save()
            elif user.permissions != permissions:
                user.permissions = permissions
                user.save(update_fields=["permissions"])

            self._link_profile(user, claims, organisation)

        return user

    def _resolve_organisation(self, claims: dict[str, Any]) -> Organisation:
        slade_code = (
            claims.get("business_partner")
            or settings.KEYCLOAK["DEFAULT_SLADE_CODE"]
        )

        if not slade_code:
            raise exceptions.AuthenticationFailed(
                "Token has no `business_partner` claim and no default is set."
            )

        try:
            organisation = Organisation.objects.get(slade_code=slade_code)
        except Organisation.DoesNotExist:
            raise exceptions.AuthenticationFailed(
                f"No organisation with slade code {slade_code}."
            ) from None

        if not organisation.active:
            raise exceptions.PermissionDenied("Inactive organisation.")

        return organisation

    def _link_profile(
        self,
        user: SILUser,
        claims: dict[str, Any],
        organisation: Organisation,
    ) -> None:
        if user.profile:
            return

        person = Person.objects.create(
            first_name=claims.get("given_name", ""),
            last_name=claims.get("family_name", ""),
            organisation=organisation,
            created_by=user.pk,
            updated_by=user.pk,
        )

        UserProfile.objects.create(
            person=person,
            user=user,
            organisation=organisation,
            created_by=user.pk,
            updated_by=user.pk,
        )

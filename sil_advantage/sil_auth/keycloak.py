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

SERVICE_TOKEN_CACHE_KEY = "keycloak_service_account_token"

# Refresh a little before expiry so a token is never handed out about to lapse.
SERVICE_TOKEN_LEEWAY = 30


def service_account_token() -> str:
    """Return a client-credentials token for calling other Empower services."""
    cached = cache.get(SERVICE_TOKEN_CACHE_KEY)
    if cached is not None:
        return cached

    try:
        response = requests.post(
            settings.KEYCLOAK["TOKEN_URL"],
            data={
                "grant_type": "client_credentials",
                "client_id": settings.KEYCLOAK["CLIENT_ID"],
                "client_secret": settings.KEYCLOAK["CLIENT_SECRET"],
            },
            timeout=settings.KEYCLOAK["TIMEOUT"],
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as error:
        raise RuntimeError(f"Could not obtain a Keycloak token: {error}") from error

    token = payload["access_token"]
    ttl = max(int(payload.get("expires_in", 60)) - SERVICE_TOKEN_LEEWAY, 1)
    cache.set(SERVICE_TOKEN_CACHE_KEY, token, ttl)

    return token


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
                # Rebuilding Keycloak issues a new subject for the same person.
                # Email is the stable identity, so adopt the existing account
                # rather than failing on the unique email.
                user = SILUser.objects.filter(email__iexact=email).first()

                if user is not None:
                    user.guid = subject
                    user.permissions = permissions
                    user.save(update_fields=["guid", "permissions"])

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


CLAIM = "business_partner"
CLAIM_CLIENTS = ("clinical", "empower-frontend")
KEYCLOAK_BUILTIN_ROLES = frozenset({"offline_access", "uma_authorization"})


class KeycloakAdmin:
    """Thin wrapper over the Keycloak admin API.

    Only what onboarding needs: the realm configuration that makes the
    `business_partner` claim exist, and creating the users that carry it.
    """

    def __init__(self) -> None:
        self.base_url = settings.KEYCLOAK["BASE_URL"]
        self.realm = settings.KEYCLOAK["REALM"]
        self.timeout = settings.KEYCLOAK["TIMEOUT"]
        self._session: Optional[requests.Session] = None

    @property
    def session(self) -> requests.Session:
        if self._session is not None:
            return self._session

        user = settings.KEYCLOAK["ADMIN_USER"]
        password = settings.KEYCLOAK["ADMIN_PASSWORD"]

        if not user or not password:
            raise RuntimeError(
                "KEYCLOAK_ADMIN_USER and KEYCLOAK_ADMIN_PASSWORD must be set to "
                "manage users."
            )

        response = requests.post(
            f"{self.base_url}/realms/{settings.KEYCLOAK['ADMIN_REALM']}"
            "/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": user,
                "password": password,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

        session = requests.Session()
        session.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
        self._session = session

        return session

    def _realm_url(self, path: str) -> str:
        return f"{self.base_url}/admin/realms/{self.realm}{path}"

    def ensure_claim_wiring(self) -> None:
        """Make the business_partner claim reach the token.

        Keycloak 24+ drops attributes the user profile does not declare, and the
        claim needs a mapper on each client. Without both, every user resolves
        to the default organisation.
        """
        url = self._realm_url("/users/profile")
        profile = self.session.get(url, timeout=self.timeout).json()

        if not any(a["name"] == CLAIM for a in profile.get("attributes", [])):
            profile.setdefault("attributes", []).append(
                {
                    "name": CLAIM,
                    "displayName": "Slade code of the user's organisation",
                    "multivalued": False,
                    "permissions": {"view": ["admin"], "edit": ["admin"]},
                    "validations": {},
                }
            )
            self.session.put(
                url, json=profile, timeout=self.timeout
            ).raise_for_status()

        for client_id in CLAIM_CLIENTS:
            self._ensure_mapper(client_id)

    def _ensure_mapper(self, client_id: str) -> None:
        clients = self.session.get(
            self._realm_url("/clients"),
            params={"clientId": client_id},
            timeout=self.timeout,
        ).json()

        if not clients:
            return

        uid = clients[0]["id"]
        mappers = self.session.get(
            self._realm_url(f"/clients/{uid}/protocol-mappers/models"),
            timeout=self.timeout,
        ).json()

        if any(m["name"] == CLAIM for m in mappers):
            return

        self.session.post(
            self._realm_url(f"/clients/{uid}/protocol-mappers/models"),
            json={
                "name": CLAIM,
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "config": {
                    "user.attribute": CLAIM,
                    "claim.name": CLAIM,
                    "jsonType.label": "String",
                    "access.token.claim": "true",
                    "id.token.claim": "true",
                    "userinfo.token.claim": "true",
                },
            },
            timeout=self.timeout,
        ).raise_for_status()

    def find_user(self, email: str) -> Optional[dict]:
        found = self.session.get(
            self._realm_url("/users"),
            params={"email": email, "exact": "true"},
            timeout=self.timeout,
        ).json()

        return found[0] if found else None

    def upsert_user(
        self,
        *,
        email: str,
        first_name: str,
        last_name: str,
        slade_code: int,
        password: Optional[str] = None,
        realm_role: str = "advantage-admin",
    ) -> bool:
        """Create or update a user. Returns True when newly created.

        A first and last name are required: Keycloak refuses to authenticate an
        account it considers incomplete.
        """
        payload = {
            "username": email,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "emailVerified": True,
            "enabled": True,
            "requiredActions": [],
            "attributes": {CLAIM: [str(slade_code)]},
        }

        existing = self.find_user(email)
        created = existing is None

        if existing:
            uid = existing["id"]
            self.session.put(
                self._realm_url(f"/users/{uid}"),
                json=payload,
                timeout=self.timeout,
            ).raise_for_status()
        else:
            response = self.session.post(
                self._realm_url("/users"), json=payload, timeout=self.timeout
            )
            response.raise_for_status()
            uid = response.headers["Location"].rsplit("/", 1)[-1]

        if password:
            self.session.put(
                self._realm_url(f"/users/{uid}/reset-password"),
                json={"type": "password", "value": password, "temporary": False},
                timeout=self.timeout,
            ).raise_for_status()

        if realm_role:
            role = self.session.get(
                self._realm_url(f"/roles/{realm_role}"), timeout=self.timeout
            )
            if role.status_code == 200:
                self.session.post(
                    self._realm_url(f"/users/{uid}/role-mappings/realm"),
                    json=[role.json()],
                    timeout=self.timeout,
                ).raise_for_status()

        return created

    def _scope_query(self, slade_code: int) -> dict[str, str]:
        """Restrict a user search to one organisation."""
        return {"q": f"{CLAIM}:{slade_code}"}

    def _is_default_org(self, slade_code: int) -> bool:
        default = settings.KEYCLOAK["DEFAULT_SLADE_CODE"]

        return bool(default) and int(default) == int(slade_code)

    def list_users(
        self,
        *,
        slade_code: int,
        search: Optional[str] = None,
        first: int = 0,
        max_results: int = 10,
    ) -> tuple[list[dict], int]:
        """Return one page of an organisation's users, and the total.

        Keycloak pages with first/max and has no total for an attribute search,
        so the match is counted by reading the whole set once. Realms here hold
        one organisation's staff, which keeps that cheap.
        """
        params: dict[str, Any] = self._scope_query(slade_code)
        if search:
            params["search"] = search

        scoped = self.session.get(
            self._realm_url("/users"),
            params={**params, "max": 1000},
            timeout=self.timeout,
        ).json()

        # Users predating the claim carry no attribute and belong to the
        # organisation the token falls back to.
        if self._is_default_org(slade_code):
            everyone = self.session.get(
                self._realm_url("/users"),
                params={**({"search": search} if search else {}), "max": 1000},
                timeout=self.timeout,
            ).json()
            known = {u["id"] for u in scoped}
            scoped += [
                u
                for u in everyone
                if u["id"] not in known
                and not (u.get("attributes") or {}).get(CLAIM)
            ]

        scoped.sort(key=lambda u: (u.get("email") or "").lower())

        return scoped[first : first + max_results], len(scoped)

    def get_user(self, user_id: str) -> Optional[dict]:
        response = self.session.get(
            self._realm_url(f"/users/{user_id}"), timeout=self.timeout
        )

        return response.json() if response.status_code == 200 else None

    def set_password(self, user_id: str, password: str) -> None:
        self.session.put(
            self._realm_url(f"/users/{user_id}/reset-password"),
            json={"type": "password", "value": password, "temporary": False},
            timeout=self.timeout,
        ).raise_for_status()

    def list_realm_roles(self) -> list[dict]:
        """Return the assignable realm roles.

        The per-permission roles are an implementation detail of the
        permission model; only the grouping roles are worth offering.
        """
        roles = self.session.get(
            self._realm_url("/roles"), params={"max": 1000}, timeout=self.timeout
        ).json()

        return sorted(
            (
                r
                for r in roles
                # Per-permission roles are an implementation detail, and
                # Keycloak's own roles are not something to assign here.
                if "." not in r["name"]
                and r["name"] not in KEYCLOAK_BUILTIN_ROLES
                # default-roles-<realm> is composed by Keycloak itself.
                and not r["name"].startswith("default-roles-")
            ),
            key=lambda r: r["name"],
        )

    def set_realm_roles(self, user_id: str, role_names: list[str]) -> None:
        wanted = []
        for name in role_names:
            response = self.session.get(
                self._realm_url(f"/roles/{name}"), timeout=self.timeout
            )
            if response.status_code == 200:
                wanted.append(response.json())

        if wanted:
            self.session.post(
                self._realm_url(f"/users/{user_id}/role-mappings/realm"),
                json=wanted,
                timeout=self.timeout,
            ).raise_for_status()


def keycloak_admin() -> KeycloakAdmin:
    """Return an admin client for the configured realm."""
    return KeycloakAdmin()

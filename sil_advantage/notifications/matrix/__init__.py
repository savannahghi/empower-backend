"""Matrix client."""
import uuid
from typing import Optional

import jwt
import requests
from asgiref.sync import async_to_sync
from django.conf import settings
from nio import AsyncClient

from sil_advantage.common.cache import cached
from sil_advantage.sil_auth.models import SILUser


@cached(ttl=45 * 60)
def get_matrix_access_token(user_id: uuid.UUID) -> dict:
    """Get the Matrix access token for a user."""
    claims = {"sub": str(user_id)}
    payload = {
        "type": "org.matrix.login.jwt",
        "token": jwt.encode(
            claims,
            settings.MATRIX_SECRET,  # type: ignore
            "HS512",
        ),
    }
    url = f"{settings.MATRIX_HOME_SERVER}/_matrix/client/r0/login"  # type: ignore
    return requests.post(url, json=payload).json()


async def get_matrix_client(
    user_id: Optional[uuid.UUID] = None,
) -> AsyncClient:
    """Get the Matrix client."""
    if user_id is None:
        client = AsyncClient(
            settings.MATRIX_HOME_SERVER,  # type: ignore
            settings.MATRIX_BOT_UID,  # type: ignore
        )
        await client.login(settings.MATRIX_BOT_PASSWORD)  # type: ignore
    else:
        token = get_matrix_access_token(user_id)
        client = AsyncClient(
            settings.MATRIX_HOME_SERVER,  # type: ignore
            user=token["user_id"],
            device_id=token["device_id"],
        )
        client.access_token = token["access_token"]
    return client


@async_to_sync
async def set_matrix_display_name(user: SILUser) -> None:
    """Set the Matrix display name for a user."""
    assert user.matrix_user_id is not None
    client = await get_matrix_client(user.guid)
    await client.set_displayname(user.full_name or "Nameless")
    await client.close()

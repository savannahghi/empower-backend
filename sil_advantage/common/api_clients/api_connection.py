"""Request creation utility."""
import io
import json
import logging
from typing import Optional

import orjson
import requests
from django.http import FileResponse

from sil_advantage.common.serializers.base import get_organisation
from sil_advantage.common.types import AuthenticatedRequest

LOGGER = logging.getLogger(__name__)


def make_request(
    method: str,
    url: str,
    request: AuthenticatedRequest,
    payload: Optional[dict | str] = None,
    custom_params: Optional[dict] = None,
    extra_headers: Optional[dict] = None,
) -> tuple[dict | str | FileResponse, int]:
    """Compose a request to the auth server API."""
    extra_headers = extra_headers or {}
    headers = {
        "Authorization": request.META.get("HTTP_AUTHORIZATION")
        or "Bearer {}".format(
            request.user.social_auth.filter(provider="sil-oauth2")  # type: ignore
            .order_by("-id")
            .first()
            .access_token
        ),
        "Content-Type": "application/json",
        "Accept": "application/json, */*",
        **extra_headers,
    }

    method = method.upper()
    if method in (
        "POST",
        "PATCH",
        "PUT",
        "DELETE",
    ):
        payload = payload if payload else {}
        organisation = get_organisation(request, payload)
        payload["organisation"] = str(organisation.id)  # type: ignore
        payload = orjson.dumps(payload).decode("utf-8")

    params: dict = dict(request.query_params.copy())
    if custom_params:
        params.update(custom_params)

    LOGGER.info("{} {}".format(method, url))
    response = requests.request(
        method, url, headers=headers, params=params, data=payload
    )

    content_disposition = response.headers.get("Content-Disposition", "")
    if "attachment" in content_disposition:
        return (
            FileResponse(io.BytesIO(response.content), as_attachment=True),
            response.status_code,
        )

    try:
        return response.json(), response.status_code
    except orjson.JSONDecodeError:
        return response.text, response.status_code
    except json.decoder.JSONDecodeError:
        return response.text, response.status_code

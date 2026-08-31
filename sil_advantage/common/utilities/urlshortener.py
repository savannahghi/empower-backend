"""Utilities for interacting with the Shlink URL shortener."""
from django.conf import settings
from sil_shlink import ShlinkPayload


def shlink_shorten_url(payload: ShlinkPayload) -> str:
    """Imported here to avoid circular imports."""
    from sil_advantage.common.api_clients.shlink import get_shlink_client

    if not isinstance(payload, ShlinkPayload):
        raise ValueError("Invalid payload provided.")

    if payload.long_url is None or payload.long_url == "":
        raise ValueError("URL to shorten is required.")

    if payload.domain is None or payload.domain == "":
        payload.domain = settings.SIL_SHLINK[  # type: ignore # import cycle issue
            "SHLINK_CUSTOM_DOMAIN"
        ]

    shlink = get_shlink_client()

    result = shlink.shorten_url(payload)

    return result["shortUrl"]

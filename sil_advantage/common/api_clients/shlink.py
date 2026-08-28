"""API client for the Shlink URL shortener service."""
from django.conf import settings
from sil_shlink import ShlinkClient


def get_shlink_client() -> ShlinkClient:
    """Returns a ShlinkClient instance."""
    api_key = settings.SIL_SHLINK["SHLINK_API_KEY"]
    shlink_url = settings.SIL_SHLINK["SHLINK_SERVER_URL"]

    return ShlinkClient(base_url=shlink_url, api_key=api_key)

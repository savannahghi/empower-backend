"""IS API Client Utilities."""
from django.conf import settings
from sil_is_client import IS


def get_is_client() -> IS:
    """Gets a IS client instance."""
    config = {
        "scheme": settings.IS_CLIENT["scheme"],
        "host": settings.IS_CLIENT["host"],
        "oauth_id": settings.IS_CLIENT["client_id"],
        "oauth_secret": settings.IS_CLIENT["client_secret"],
        "user_email": settings.IS_CLIENT["username"],
        "user_password": settings.IS_CLIENT["password"],
        "token_url": settings.IS_CLIENT["token_url"],
    }
    is_client = IS(config)
    return is_client

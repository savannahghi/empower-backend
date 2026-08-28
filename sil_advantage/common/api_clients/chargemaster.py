"""Chargemaster API Client Utilities."""
from charge_master_client import ChargeMaster
from django.conf import settings


def get_chargemaster_client() -> ChargeMaster:
    """Gets a chargemaster client instance."""
    config = {
        "scheme": settings.CHARGE_MASTER["scheme"],
        "host": settings.CHARGE_MASTER["host"],
        "oauth_id": settings.CHARGE_MASTER["client_id"],
        "oauth_secret": settings.CHARGE_MASTER["client_secret"],
        "user_email": settings.CHARGE_MASTER["username"],
        "user_password": settings.CHARGE_MASTER["password"],
        "token_url": settings.CHARGE_MASTER["token_url"],
    }
    chargemaster = ChargeMaster(config)
    return chargemaster

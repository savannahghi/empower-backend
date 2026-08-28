"""ERP API Client Utilities."""
from typing import Any, Optional
from uuid import UUID

from django.conf import settings
from sil_erp_client import ERP

from sil_advantage.common.cache import cached


def get_erp_client(workstation_id: Optional[UUID]) -> ERP:
    """Get ERP client and set the necessary headers."""
    config = {**settings.ERP_API_CONFIG}
    erp = ERP(**config)
    erp.conn.base_headers["X-Workstation"] = str(workstation_id)
    erp.conn.base_headers["User-Agent"] = settings.API_USER_AGENT
    return erp


@cached(ttl=86_400)
def fetch_from_erp_cache(
    resource_name: str,
    method: str,
    *args: Any,
    **kwargs: Any,
) -> dict:
    """Fetch data from the ERP cache if available."""
    erp = get_erp_client(None)
    resource = getattr(erp, resource_name)
    endpoint = getattr(resource, method)
    return endpoint(*args, **kwargs)

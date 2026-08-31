"""Shared serializer mixins."""
from typing import Optional

from sil_advantage.common.types import AuthenticatedRequest


class PartialResponseMixin:
    """Mixin that allows API clients to specify fields."""

    def strip_fields(
        self,
        request: AuthenticatedRequest,
        origi_fields: dict,
    ) -> dict:
        """Select a subset of fields, determined by the `fields` parameter.

        Fetch a subset of fields from the serializer determined by the
        request's ``fields`` query parameter.

        This is an initial implementation that does not handle:
          - nested relationships
          - rejection of unknown fields (currently ignoring unknown fields)
          - wildcards
          - e.t.c
        """
        if request is None or not hasattr(request, "query_params"):
            return origi_fields

        request_method: Optional[str] = ""

        if hasattr(request, "method"):
            request_method = request.method

        if request_method != "GET":
            return origi_fields

        fields = request.query_params.get("fields", None)
        if isinstance(fields, str) and fields:
            fields_list = [f.strip() for f in fields.split(",")]
            return {
                field: origi_fields[field]
                for field in origi_fields
                if field in fields_list
            }
        return origi_fields

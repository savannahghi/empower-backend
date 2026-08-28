"""Common manager."""
from typing import Any


class CommonFieldsManager:
    """Handles common fields for models."""

    def __init__(self, code: Any):
        """Initialize."""
        self.organisation = code.organisation
        self.created_by = code.created_by
        self.updated_by = code.updated_by
        self.cluster_id = code.cluster_id
        self.branch_id = code.branch_id
        self.department_id = code.department_id
        self.workstation_id = code.workstation_id

    def get_common_fields(self) -> dict:
        """Return common fields as a dictionary."""
        return {
            "organisation": self.organisation,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "cluster_id": self.cluster_id,
            "branch_id": self.branch_id,
            "department_id": self.department_id,
            "workstation_id": self.workstation_id,
        }

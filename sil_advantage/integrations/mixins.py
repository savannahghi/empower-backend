"""Integrations mixins."""
import logging
import uuid
from functools import cached_property
from typing import Any, Callable, Literal

from django.conf import settings
from django.db import transaction
from django.db.models.base import Model, ModelState
from django.db.models.options import Options
from orjson import JSONDecodeError
from sil_erp_client import ERP
from sil_wrapper_utils.exceptions import ItemNotFound

from sil_advantage.common.models import Organisation, OrgUnit
from sil_advantage.integrations.tasks import sync_updates_to_remote

LOGGER = logging.getLogger(__file__)


class RemoteObjectMixin:
    """Model mixin that abstracts away updating resources in remote systems.

    Models simply inherit this class & update the `_remote_obj_refs` variable.

    Example from `billing.BillableItem`:

    _remote_obj_refs = {
        "ERP": [  # ERP is the system
            (
                "sales_order_lines",  # identifies the resource/api name
                {
                    "sales_order_line_id": "id",  # fields mapping, 1st must be IDs
                },
            ),
            (
                "sales_invoice_lines",  # we can link to multiple resources
                {
                    "sales_invoice_line_id": "id",
                },
            ),
        ],
    }
    Remote resources that are dependencies to other remote resource
    should come first. From the example above, a sales invoice line
    depends on a sales order line in the ERP.

    Example from `billing.Invoice`:

    _remote_obj_refs = {
        "ERP": [
            (
                "sales_invoices",
                {
                    "sales_invoice_id": "id",
                    # fields that must match on both systems
                    # and are updated automatically
                    "invoice_number": "document_number",
                    "workflow_state": "workflow_state",
                },
            ),
        ],
    }

    One should also add a property to tell this mixin how to construct payloads.
    This should follow the format: `{system}_{resource_name}_payload`
    """

    # RemoteObjectMixin fields
    _remote_obj_refs: dict[str, list[tuple[str, dict[str, str]]]] = {}
    _disable_sync: bool = False

    # Django model attributes & methods
    pk: uuid.UUID
    full_clean: Callable
    _state: ModelState
    _meta: Options

    # OrgUnitIdsMixin fields
    workstation_id: uuid.UUID
    department_id: uuid.UUID
    branch_id: uuid.UUID
    cluster_id: uuid.UUID
    organisation: Organisation

    # Audit fields
    created_by: uuid.UUID
    updated_by: uuid.UUID

    # Tasks
    # run task `sync_eta` seconds from now
    sync_eta: int = 0
    async_enabled: bool = True

    @cached_property
    def erp_client(self) -> ERP:
        """Return the ERP Client."""
        # import's here due to circular dependency issues
        from sil_advantage.common.api_clients.erp import get_erp_client

        return get_erp_client(self.workstation_id)

    @cached_property
    def health_crm_client(self) -> Any:
        """Return the HealthCRM Client."""
        from sil_advantage.common.api_clients.health_crm import HealthCRMClient

        return HealthCRMClient()

    @cached_property
    def clinical_service_client(self) -> Any:
        """Return the clinical service client."""
        from sil_advantage.common.api_clients.clinical import (
            ClinicalServiceClient,
        )

        org_unit = OrgUnit.objects.get(
            organisation=self.organisation,
            erp_id=self.branch_id,
        )
        assert self.organisation.tenant_id is not None
        return ClinicalServiceClient(
            self.organisation.tenant_id,
            org_unit.facility_id,
        )

    def _perform_operation_on_erp(
        self,
        operation: Literal[
            "CREATE",
            "UPDATE",
            "DELETE",
        ],
    ) -> None:
        """Perform an operation on the ERP."""
        remote_obj_refs = self._remote_obj_refs["ERP"]

        if operation == "DELETE":
            # objects that come later in the list
            # are assumed to depend on the items that came first
            # so we have to delete the "child" objects first
            # then delete the "parents"
            # this is useful for deleting objects that are protected
            # in foreign-key relations on the remote system
            remote_obj_refs.reverse()

        for remote_obj_ref in remote_obj_refs:
            resource_name = remote_obj_ref[0]
            fields_mapping = remote_obj_ref[1]

            local_id_field_name = next(iter(fields_mapping.items()))[0]
            remote_id_value = getattr(self, local_id_field_name)
            exists_on_remote = remote_id_value is not None

            resource = getattr(self.erp_client, resource_name)

            if operation in ("CREATE", "UPDATE"):
                payload_property_name = f"erp_{resource_name}_payload"
                payload = getattr(self, payload_property_name)
                if payload is None:
                    LOGGER.warning(
                        f"Payload {payload_property_name} of "
                        f"object with ID {self.pk} of type "
                        f"{self._meta.app_label}.{self._meta.model_name} "  # type: ignore
                        f"returned None (operation: {operation})"
                    )
                    continue

                payload["created_by"] = str(self.created_by)
                payload["updated_by"] = str(self.updated_by)

                if exists_on_remote:
                    result = resource.update(remote_id_value, payload)
                else:
                    result = resource.create(payload)

                self._update_local_fields(fields_mapping, result)
            elif operation == "DELETE" and exists_on_remote:
                try:
                    result = resource.delete(remote_id_value)
                except (
                    ItemNotFound,
                    JSONDecodeError,
                ):
                    pass
            else:
                LOGGER.warning(f"Unsupported operation {operation}")

    def _perform_operation_on_health_crm(
        self,
        operation: Literal[
            "CREATE",
            "UPDATE",
            "DELETE",
        ],
    ) -> None:
        """Perform an operation on Health CRM."""
        from sil_advantage.patients.models import SYNC_STATUS

        remote_obj_refs = self._remote_obj_refs["HEALTH_CRM"]
        for remote_obj_ref in remote_obj_refs:
            resource_name = remote_obj_ref[0]
            resource = getattr(self.health_crm_client, resource_name)

            payload_property_name = f"health_crm_{resource_name}_payload"
            payload = getattr(self, payload_property_name)
            try:
                resource.create(payload)
                self.health_crm_sync_status = dict(SYNC_STATUS)["SUCCESS"]
            except Exception as e:
                LOGGER.error(f"Health CRM operation CREATE failed: {e}")
                self.health_crm_sync_status = dict(SYNC_STATUS)["FAILED"]

            self._disable_sync = True
            self.save(update_fields=["health_crm_sync_status"])
            self._disable_sync = False

    def _perform_operation_on_clinical_service(
        self,
        operation: Literal[
            "CREATE",
            "UPDATE",
            "DELETE",
        ],
    ) -> None:
        """Perform an operation on the Clinical Service."""
        remote_obj_refs = self._remote_obj_refs["CLINICAL_SERVICE"]
        for remote_obj_ref in remote_obj_refs:
            resource_name = remote_obj_ref[0]
            fields_mapping = remote_obj_ref[1]

            local_id_field_name = next(iter(fields_mapping.items()))[0]
            remote_id_value = getattr(self, local_id_field_name)
            exists_on_remote = remote_id_value is not None

            if not exists_on_remote and operation == "UPDATE":
                operation = "CREATE"

            mutation = f"{operation.lower()}_{resource_name}"
            op = getattr(
                self.clinical_service_client,
                mutation,
                None,
            )
            if op is None:
                # some endpoints don't have update and delete mutations
                LOGGER.warning(f"Mutation {mutation} not implemented")
                continue

            if operation in ("CREATE", "UPDATE"):
                payload_property_name = f"clinical_service_{resource_name}_payload"
                payload = getattr(self, payload_property_name)

                if exists_on_remote:
                    result = op(remote_id_value, payload)
                else:
                    result = op(payload)

                self._update_local_fields(fields_mapping, result)
            elif operation == "DELETE" and exists_on_remote:
                op(remote_id_value)
            else:
                LOGGER.warning(f"Unsupported operation {operation}")

    def _perform_delete_synchronously(self) -> None:
        """Perform a delete synchronously."""
        for system in self._remote_obj_refs.keys():
            if system == "ERP" and settings.SYNC_WITH_ERP:
                self._perform_operation_on_erp("DELETE")
            elif system == "CLINICAL_SERVICE" and settings.SYNC_WITH_CLINICAL_SERVICE:
                self._perform_operation_on_clinical_service("DELETE")

    def _update_local_fields(
        self,
        fields_mapping: dict[str, str],
        result: dict[str, Any],
    ) -> None:
        """Update local fields with result from remote.

        `fields_mapping` example:
            BillableItem's mapping to ERP's `sales_invoice_lines`:
                {
                    "sales_invoice_line_id": "id",
                    "price": "new_price",
                }
        """
        # The clients report a failed call by returning an error rather than
        # raising, and a partial remote response is possible too. Either way the
        # local record stays unsynced for the retry task to pick up; failing the
        # write would lose data this service is the system of record for.
        missing = [f for f in fields_mapping.values() if f not in result]
        if missing:
            LOGGER.error(
                "Not updating %s from remote: response is missing %s",
                self._meta.model_name,
                ", ".join(missing),
                extra={"result": result},
            )

            return

        sync_attr = "_disable_sync"
        with transaction.atomic():
            # Lock the current object for updating
            # to prevent overwriting by multiple tasks
            # running simultaneously.
            # Transactions waiting to update will block
            # until the lock is released.
            obj: Model = self._meta.model.objects.select_for_update(
                nowait=False,
                skip_locked=False,
                # acquire a weaker lock to allow inserting related rows
                # with foreign keys to this row
                no_key=True,
                of=("self",),
            ).get(pk=self.pk)

            update_fields = []
            for local_field, remote_field in fields_mapping.items():
                setattr(obj, local_field, result[remote_field])
                update_fields.append(local_field)

            setattr(obj, sync_attr, True)
            obj.save(update_fields=update_fields)

            # Refresh the current object with data from the DB
            for field in self._meta.fields:
                value = getattr(obj, field.name)
                setattr(self, field.name, value)

    def _dispatch(
        self,
        operation: Literal[
            "CREATE",
            "UPDATE",
            "DELETE",
        ],
    ) -> None:
        """Perform operations on multiple systems asynchronously."""
        if operation == "DELETE":
            self._perform_delete_synchronously()
            return

        model = f"{self._meta.app_label}.{self._meta.model_name}"  # type: ignore
        for system in self._remote_obj_refs.keys():
            if system == "ERP" and settings.SYNC_WITH_ERP:
                sync_updates_to_remote.apply_async(
                    queue=settings.CELERY_DEFAULT_QUEUE,
                    priority=settings.CELERY_TASK_HIGH_PRIORITY,
                    countdown=self.sync_eta,
                    args=(
                        model,
                        self.pk,
                        "ERP",
                        operation,
                    ),
                )
            elif system == "HEALTH_CRM" and settings.SYNC_WITH_HEALTH_CRM:
                sync_updates_to_remote.apply_async(
                    queue=settings.CELERY_DEFAULT_QUEUE,
                    priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
                    countdown=self.sync_eta,
                    args=(
                        model,
                        self.pk,
                        "HEALTH_CRM",
                        operation,
                    ),
                )
            elif system == "CLINICAL_SERVICE" and settings.SYNC_WITH_CLINICAL_SERVICE:
                if self.async_enabled:
                    sync_updates_to_remote.apply_async(
                        queue=settings.CELERY_DEFAULT_QUEUE,
                        priority=settings.CELERY_TASK_HIGH_PRIORITY,
                        countdown=self.sync_eta,
                        args=(
                            model,
                            self.pk,
                            "CLINICAL_SERVICE",
                            operation,
                        ),
                    )
                else:
                    sync_updates_to_remote(
                        model, self.pk, "CLINICAL_SERVICE", operation
                    )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Intercept model saves to create and update on remote."""
        self.full_clean()

        adding = self._state.adding
        super().save(*args, **kwargs)  # type: ignore  # inheritance be wildin'

        if adding:
            self._dispatch("CREATE")
        elif not self._disable_sync:  # prevent infinite recursion
            self._dispatch("UPDATE")
        self._disable_sync = False

    def delete(self, *args: Any, **kwargs: Any) -> None:
        """Delete both locally and on the remote system(s)."""
        if not self._disable_sync:
            self._dispatch("DELETE")
        super().delete(*args, **kwargs)  # type: ignore  # inheritance be wildin'

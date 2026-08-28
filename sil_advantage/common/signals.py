"""Common Django signals."""
import uuid
from typing import Any, Optional

from django.db.models import Model
from django.dispatch import Signal, receiver

from sil_advantage.common.models import InstanceHistory, Organisation

""" Tracking Instance History. """

post_instance_save = Signal()


@receiver(post_instance_save)
def save_instance_snapshot(
    sender: Model,
    organisation: Organisation,
    instance_id: uuid.UUID,
    snapshot: dict,
    **kwargs: Any,
) -> None:
    """Save instance snapshot."""
    model_name = f"{sender._meta.app_label}.{sender._meta.model_name}"

    existing: Optional[InstanceHistory] = None
    try:
        existing = InstanceHistory.objects.filter(
            model_name=model_name,
            instance_id=instance_id,
        ).latest("created")
    except InstanceHistory.DoesNotExist:
        pass

    if existing is None or existing.snapshot != snapshot:
        InstanceHistory.objects.create(
            organisation=organisation,
            instance_id=instance_id,
            model_name=model_name,
            snapshot=snapshot,
            created_by=organisation.created_by,
            updated_by=organisation.updated_by,
        )

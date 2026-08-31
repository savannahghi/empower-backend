"""Integration models."""
from django.contrib.postgres.fields import ArrayField
from django.db import models

from sil_advantage.common.fields import EncryptedJsonField
from sil_advantage.common.models import OwnerlessAbstractBase


class IntegrationConfig(OwnerlessAbstractBase):
    """Integration Config.

    In the spirit of "configuration as data".
    """

    system = models.CharField(
        max_length=64,
        choices=[("GOOGLE_DRIVE", "GOOGLE_DRIVE")],
    )
    role = models.CharField(
        max_length=64,
        choices=[("PATIENT_RECORDS_UPLOAD", "PATIENT_RECORDS_UPLOAD")],
    )
    # config such as access & refresh tokens, API keys, etc
    config = EncryptedJsonField(default=None, null=True, blank=True)
    organisations = ArrayField(
        base_field=models.IntegerField(),  # slade codes
        default=list,
        blank=True,
    )
    metadata = models.JSONField(default=dict, blank=True)

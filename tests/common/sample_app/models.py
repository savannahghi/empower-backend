"""Sample test models."""
from django.db import models

from sil_advantage.common.models import AbstractBase


class ABC(AbstractBase):
    """Sample model."""

    jina = models.CharField(max_length=255)
    siku = models.DateTimeField()


class Animals(models.Model):
    """Sample model."""

    name = models.CharField(max_length=255)
    created_by = models.UUIDField()
    created_by_name = "Nyagidez"

"""Models for the test app."""
import uuid

from django.db import models

from sil_advantage.common.models.base import AbstractBase


class TestAbstractBase(models.Model):
    """Define the Test Abstracr base model."""

    name = models.CharField(max_length=55)
    created = models.DateTimeField(auto_now=True)
    updated = models.DateTimeField(auto_now=True)
    base_uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        """Define model options."""

        abstract = True
        app_label = "test_app"
        ordering = ("-id",)


class CustomMeta(TestAbstractBase):
    """Define the CustomMeta model.Inherit abstract base model fields."""

    choice = models.CharField(max_length=255, choices=(("A", "a"), ("B", "b")))

    class Meta:
        """Define model options."""

        app_label = "test_app"


class TestCustom(TestAbstractBase):
    """Define the TestCustom model.Inherit abstract base model fields."""

    custom_meta = models.ForeignKey(CustomMeta, on_delete=models.PROTECT)
    test_name = models.CharField(max_length=10)

    class Meta:
        """Define app name for model."""

        app_label = "test_app"


class FkCustomMeta(models.Model):
    """Define the FkCustomMeta model."""

    my_custom_meta = models.ForeignKey("MtoMCustomMeta", on_delete=models.PROTECT)
    custom_meta = models.ForeignKey(CustomMeta, on_delete=models.PROTECT)

    class Meta:
        """Define app name and odering for model."""

        app_label = "test_app"
        ordering = ("-id",)


class MtoMCustomMeta(models.Model):
    """Define MtoMCustomMeta model."""

    dec = models.DecimalField(max_digits=10, decimal_places=2, default=25.25)
    date = models.DateField(auto_now=True)
    custom_meta = models.ForeignKey(CustomMeta, on_delete=models.PROTECT)
    custom_metas = models.ManyToManyField(CustomMeta, related_name="custom_metas")
    my_custom_metas = models.ManyToManyField("self")
    others = models.ManyToManyField(
        CustomMeta, through=FkCustomMeta, related_name="other_custom_meta"
    )

    class Meta:
        """Defoine app name for model."""

        app_label = "test_app"
        ordering = ("-id",)


class Parent(AbstractBase):
    """Define the TestCustom model.Inherit abstract base model fields."""

    name = models.CharField(max_length=50)

    class Meta:
        """Define app name and odering for model."""

        ordering = ("-id",)
        app_label = "test_app"


class ParentNote(AbstractBase):
    """Define the TestCustom model.Inherit abstract base model fields."""

    note = models.TextField()
    parent = models.ForeignKey(Parent, on_delete=models.PROTECT)

    class Meta:
        """Define app name and odering for model."""

        app_label = "test_app"
        ordering = ("-id",)


class Child(AbstractBase):
    """Define the TestCustom model.Inherit abstract base model fields."""

    name = models.CharField(max_length=50)
    parent = models.ForeignKey(Parent, on_delete=models.PROTECT)

    class Meta:
        """Define app name and odering for model."""

        app_label = "test_app"
        ordering = ("-id",)

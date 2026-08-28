"""Custom fields and field serializers."""
from typing import Optional

from phonenumber_field.phonenumber import PhoneNumber, to_python
from rest_framework import serializers


class PhoneNumberFieldSerializer(serializers.CharField):
    """Custom phone number field serializer."""

    def to_internal_value(self, data: Optional[str]) -> PhoneNumber:
        """Transform phone number to its Python representation."""
        return to_python(data)

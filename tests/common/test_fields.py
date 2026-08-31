"""Test for various fields."""
from django.test import SimpleTestCase
from phonenumbers import PhoneNumber

from sil_advantage.common.utilities.fields import PhoneNumberFieldSerializer


class TestPhoneNumberFieldSerializer(SimpleTestCase):
    """Test for phone number field serializer."""

    def test_to_internal_val_success(self):
        """Test for internal val success."""
        f = PhoneNumberFieldSerializer()
        res = f.to_internal_value("+254723466938")
        assert isinstance(res, PhoneNumber)

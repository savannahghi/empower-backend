"""App used during tests."""
import orjson
from django.apps import AppConfig
from django.contrib.postgres.fields.array import ArrayField
from django.db.models import JSONField
from phonenumber_field.modelfields import PhoneNumberField


def gen_func():
    """Create test value."""
    return "value"


def phone_number():
    """Create test phone number."""
    return "+254722123848"


def gen_json():
    """Generate test json data."""
    return orjson.dumps({"k": "v"}).decode("utf-8")


def gen_array():
    """Generate random test array of no."""
    return list(range(10))


class TestAppConfig(AppConfig):
    """Configuration used when running tests."""

    name = "tests.common.test_app"

    def ready(self):
        """Define generators methods for custom fields."""
        from model_bakery import baker

        baker.generators.add(PhoneNumberField, phone_number)
        baker.generators.add(JSONField, gen_json)
        baker.generators.add(ArrayField, gen_array)

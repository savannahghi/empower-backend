"""Test the model validations mixin."""
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError

from sil_advantage.common.models import ValidationErrorsMixin


class DictError(ValidationErrorsMixin):
    """Raise validation errors with a dict."""

    class Meta:
        """Define app name for the model."""

        app_label = "dict_error"

    model_validators = [
        "validation_one",
        "validation_two",
        "validation_three",
        "validation_four",
        "validation_one",  # duplicate
    ]

    def validation_one(self):
        """Define first validation raise with a dictionary."""
        raise ValidationError({"field_1": "Error!", "field_2": "Error!"})

    def validation_two(self):
        """Define second validation raise with a dictionary."""
        raise ValidationError({"field_1": "Error2!"})

    def validation_three(self):
        """Define third validation raise with a message."""
        raise ValidationError("plain error")

    def validation_four(self):
        """Define fourth validation raise with a list of messages."""
        raise ValidationError(["list error one", "list error two"])


def test_run_model_validators():
    """Test model validation."""
    instance = DictError()
    with pytest.raises(ValidationError) as e:
        instance.run_model_validators()

    assert e.value.message_dict == {
        "field_1": ["Error!", "Error2!"],
        "field_2": ["Error!"],
        "__all__": ["plain error", "list error one", "list error two"],
    }


def test_duplicate_validator_ignored():
    """Test same validator not run twice on a model."""
    instance = DictError()
    with patch.object(instance, "validation_one") as validation_one:
        with pytest.raises(ValidationError):
            instance.run_model_validators()

    validation_one.assert_called_once_with()

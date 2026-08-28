"""Common model mixins."""
from collections import defaultdict
from typing import Any, Callable

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.base import ModelBase
from sil_transitions import TransitionAndLogMixin


class OrgUnitIdsMixin(models.Model):
    """Adds Org unit IDs & workstation IDs to a model."""

    workstation_id = models.UUIDField(null=True, blank=True, db_index=True)
    department_id = models.UUIDField(null=True, blank=True, db_index=True)
    branch_id = models.UUIDField(null=True, blank=True, db_index=True)
    cluster_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        """Make `OrgUnitIdsMixin` abstract."""

        abstract = True


class ValidationMetaclass(ModelBase):
    """Ensures model_validators defined in parent are retained in child models.

    For example:

        class Parent(models.Model):
            model_validators = ["a"]

        class Child(models.Model(Parent):
            model_validators = ["b"]

        assert Child().model_validators == ["a", "b"]  # True
    """

    def __new__(cls, name: str, bases: dict, attrs: dict):  # type: ignore
        """Customize the model metaclass - add support for model_validators."""
        _model_validators = []
        for each in bases:
            if hasattr(each, "model_validators"):
                _model_validators.extend(each.model_validators)
        _model_validators.extend(attrs.get("model_validators", []))
        attrs["model_validators"] = _model_validators
        return super(ValidationMetaclass, cls).__new__(  # type: ignore
            cls,
            name,
            bases,
            attrs,
        )


class ValidationErrorsMixin:
    """Run all model validations and aggregate errors.

    Errors are aggregated in either of the following ways:

    - if validation error was raised with a dict, aggregate the messages under
        the relevant key
    - if validation was raised with a message / list of messages, aggregate the
        messages under __all__ key
    """

    full_clean: Callable

    def _raise_errors(self, errors: dict) -> None:
        if errors:
            raise ValidationError(errors)

    def run_model_validators(self) -> None:
        """Ensure that all model validators run."""
        validators = getattr(self, "model_validators", [])
        self.run_validators(validators)

    def run_validators(self, validators: list[str]) -> None:
        """Run declared model validators."""
        errors = defaultdict(list)

        unique_list = dict.fromkeys(validators).keys()
        for validator in unique_list:
            try:
                getattr(self, validator)()
            except ValidationError as e:
                if hasattr(e, "error_dict"):
                    for key, messages in e.message_dict.items():
                        # messages is ValidationError instances list
                        errors[key].extend(messages)
                else:
                    errors["__all__"].extend(e.messages)

        self._raise_errors(errors)

    def clean(self) -> None:
        """Run validators declared under model_validators."""
        self.run_model_validators()
        super().clean()  # type: ignore  # inheritance be wildin'

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Run full validation with each save."""
        self.full_clean()
        super().save(*args, **kwargs)  # type: ignore  # inheritance be wildin'


class TransitionValidationMixin(TransitionAndLogMixin):
    """Add transition validation to `TransitionAndLogMixin`.

    Brought in from the SIL Comms project.
    """

    def create_transition_log(self) -> None:
        """Create a state change transition log."""
        data = self.transition_log_data()
        data.update(
            {
                "created_by": self.created_by,
                "updated_by": self.updated_by,
                "organisation": self.organisation,
                self._transition_field: getattr(self, self._transition_field),
            }
        )
        log_kwargs = getattr(self, "_transition_log_kwargs", {})
        data.update(log_kwargs)
        self._transition_log_model._default_manager.create(**data)

    def validate_transition(self) -> None:
        """Validate that the state change is valid."""
        previous_state = self._old_transition_value
        new_state = getattr(self, self._transition_field)
        state_changed = previous_state != new_state
        valid = self.can_transition_to(previous_state, new_state)
        if not valid and state_changed:
            err_msg = f"Invalid transition from {previous_state} to {new_state}"
            raise ValidationError({self._transition_field: err_msg})

    def clean(self) -> None:
        """Validate fields before saving."""
        self.validate_transition()
        super().clean()

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Validate fields before saving."""
        self.full_clean()
        super().save(*args, **kwargs)

"""Settings registry."""
from dataclasses import dataclass
from typing import Any, Callable, Optional

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


@dataclass
class SettingManager:
    """Manage a setting's configuration."""

    name: str
    description: str
    default: object
    type: type
    validator: Optional[Callable[..., bool]] = None
    deprecated: bool = False

    def __post_init__(self) -> None:
        """Run validation checks after class initialization."""
        self.validate()

    def validate(self, value: Any = None) -> bool:
        """Validate that the preference being stored is correct."""
        if value is None:
            value = self.default

        if not isinstance(value, self.type):
            raise TypeError(
                f"Preference has invalid type {type(value)}, expecting {self.type}."
            )

        if self.validator is not None and self.validator(value) is False:
            raise ValidationError(_("Preference validation failed."))

        return True

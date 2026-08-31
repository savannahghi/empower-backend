"""USSD Custom Validator."""

import re
from typing import Any, Callable, Dict

from sil_advantage.notifications.ussd.validators.base_validator import (
    BaseValidator,
)


class CustomValidator(BaseValidator):
    """Custom Validator for specific USSD input validation."""

    def get_validations(self) -> Dict[str, Callable[[str, Dict[str, Any]], bool]]:
        """Return a dictionary of state-specific validation functions."""
        return {
            "ENTER_NAME": lambda inp, ctx: bool(re.match(r"^\w+\s+\w+$", inp)),
            "ENTER_DOB": lambda inp, ctx: self.validate_date(inp),
            "ENTER_GENDER": lambda inp, ctx: inp in ["0", "1", "2", "3"],
            "CONSENT_SMS": lambda inp, ctx: inp in ["0", "1", "2"],
            "CONFIRM_ENROLLMENT": self.validate_segment_selection,
        }

    @staticmethod
    def validate_date(date_str: str) -> bool:
        """Validate date format DD/MM/YYYY."""
        try:
            day, month, year = map(int, date_str.split("/"))
            return 1 <= day <= 31 and 1 <= month <= 12 and year > 1900
        except ValueError:
            return False

    @staticmethod
    def validate_segment_selection(user_input: str, context: Dict[str, Any]) -> bool:
        """Validate user input for segment selection."""
        selected_index = int(user_input) - 1
        return 0 <= selected_index < len(context)

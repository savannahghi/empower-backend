"""USSD Base Validator."""
from typing import Any, Callable, Dict, Optional, Union


class BaseValidator:
    """Base Validator for USSD input validation."""

    def __init__(self, messages: Dict[str, Dict[str, str]]):
        """Initialize."""
        self.messages = messages
        self.validators = self.wrap_validators(self.get_validations())

    def get_validations(self) -> Dict[str, Callable[[str, Dict[str, Any]], bool]]:
        """Get validators. To be overridden in subclasses."""
        return {}  # pragma: no cover

    def wrap_validators(
        self, validators: Dict[str, Callable[[str, Dict[str, Any]], bool]]
    ) -> Dict[str, Callable[[str, Dict[str, Any]], bool]]:
        """Wrap validators to handle '0' input for going back to the main menu."""

        def wrapped_validator(
            validator: Callable[[str, Dict[str, Any]], bool]
        ) -> Callable[[str, Dict[str, Any]], bool]:
            def wrapped(user_input: str, context: Dict[str, Any]) -> bool:
                if user_input == "0":
                    return True
                return validator(user_input, context)

            return wrapped

        return {
            state: wrapped_validator(validator)
            for state, validator in validators.items()
        }

    def validate(
        self,
        current_state: str,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Union[str, bool]]:
        """Validate user input based on the current state."""
        context = context or {}
        validator_func = self.validators.get(current_state, lambda inp, ctx: True)
        is_valid = validator_func(user_input, context)

        if not is_valid:
            error_message = (
                f"CON Invalid input. Please enter correct data for "
                f"{current_state.lower()} again."
            )
            next_state = current_state
        else:
            error_message = ""
            next_state = ""

        return {
            "is_valid": is_valid,
            "message": error_message,
            "next_state": next_state,
        }

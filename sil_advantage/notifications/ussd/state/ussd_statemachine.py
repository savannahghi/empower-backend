"""USSD Statemachine."""
from typing import Any, Dict


class USSDStateMachine:
    """USSD Session State Machine."""

    def __init__(
        self,
        state_definitions: Dict[str, Dict[str, Any]],
        messages: Dict[str, Dict[str, Any]],
    ):
        """Initialize the USSDStateMachine with state definitions and messages."""
        self.state_definitions = state_definitions
        self.messages = messages

    def handle_input(
        self, current_state: str, user_input: str, language: str
    ) -> Dict[str, str]:
        """Handle user input and transition to the next state."""
        state_info = self.state_definitions.get(current_state, {})
        next_state = state_info["next_state"].get(
            user_input, state_info["next_state"].get("default")
        )
        if not user_input.strip():
            return {
                "message": self.messages[language]["LANGUAGE_SELECTION"],
                "next_state": "LANGUAGE_SELECTION",
            }
        if next_state is None:
            return {
                "next_state": current_state,
            }

        next_state_message = self.messages.get(language, {}).get(
            next_state, "END Invalid state."
        )
        return {"message": next_state_message, "next_state": next_state}

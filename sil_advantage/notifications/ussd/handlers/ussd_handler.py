"""USSD utilities."""
import logging
from typing import Any, Dict

from sil_advantage.notifications.ussd.managers.patient_manager import (
    PatientManager,
)
from sil_advantage.notifications.ussd.managers.session_manager import (
    SessionManager,
)
from sil_advantage.notifications.ussd.state.ussd_statemachine import (
    USSDStateMachine,
)
from sil_advantage.notifications.ussd.validators.custom_validator import (
    CustomValidator,
)

logger = logging.getLogger(__name__)


class USSDHandler:
    """Class to handle USSD logic."""

    def __init__(
        self,
        state_machine: USSDStateMachine,
        session_manager: SessionManager,
        validator: CustomValidator,
    ):
        """Initialize the handler with a state machine and session manager."""
        self.state_machine = state_machine
        self.session_manager = session_manager
        self.validator = validator

    def handle_request(
        self, session_id: str, user_input: str, phone_number: str, ussd_code: str
    ) -> Dict[str, Any]:
        """Process the USSD request and generate a response."""
        inputs = user_input.split("*")
        session = self.session_manager.get_session(session_id)
        session["session_id"] = session_id
        current_state = session.get("state", "LANGUAGE_SELECTION")
        language = session.get("language", "en")

        input_part = inputs[-1].strip()

        if current_state == "LANGUAGE_SELECTION":
            language = {"1": "en", "2": "sw"}.get(input_part, language)
            session["language"] = language
            # Update the language for the person in the database
            self._update_language_for_person(session, phone_number, ussd_code)

        context = {"segments": session.get("segments", []), "language": language}

        # Validate the user input
        validation_result = self.validator.validate(current_state, input_part, context)
        if not validation_result["is_valid"]:
            response_message = validation_result["message"]
            return {"message": response_message}

        # Handle state transition and store the input
        response = self.state_machine.handle_input(current_state, input_part, language)
        next_state = response["next_state"]
        session["state"] = next_state
        session[current_state] = input_part
        self.session_manager.save_session(session_id, session)

        response_message = self.handle_state(
            next_state, session, phone_number, ussd_code
        )
        if response_message.startswith("END"):
            self.session_manager.delete_session(session_id)

        return {"message": response_message}

    def handle_state(
        self, state: str, session: Dict[str, Any], phone_number: str, ussd_code: str
    ) -> str:
        """Handle state-specific logic. To be implemented by subclasses."""
        raise NotImplementedError()  # pragma: no cover

    @staticmethod
    def _update_language_for_person(
        session: Dict[str, Any], phone_number: str, ussd_code: str
    ) -> None:
        """Update the language of the person.

        Args:
            person (Person): The person whose language is to be updated.
            new_language (str): The new language to set for the person.

        Returns:
            None
        """
        try:
            patient_details = session.get("patient_details")

            if not patient_details:
                patient_details = PatientManager.check_patient_exists(
                    phone_number, ussd_code
                )

            if patient_details and hasattr(patient_details, "person"):
                person = patient_details.person
                selected_language = session["language"]

                if not person.language or person.language != selected_language:
                    person.language = selected_language
                    person.save()
                    logger.info(
                        f"Successfully updated language for person ID {person.id} to "
                        f"{selected_language}"
                    )
                else:
                    logger.info(
                        f"Language for person ID {person.id} is "
                        "already {selected_language}, no update needed."
                    )
            else:
                logger.error(
                    "Patient details not found or does not have a person attribute."
                )

        except Exception as e:
            logger.error(f"Error updating language for person ID: {e}")

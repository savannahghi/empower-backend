"""Self registration handler."""
from typing import Any, Dict

from sil_advantage.notifications.ussd import (
    CONSENT_DICT,
    GENDER_DICT,
    GENDER_DICT_SWAHILI,
)
from sil_advantage.notifications.ussd.handlers.ussd_handler import USSDHandler
from sil_advantage.notifications.ussd.managers.operation_region_manager import (
    RegionManager,
)
from sil_advantage.notifications.ussd.managers.patient_manager import (
    PatientManager,
)
from sil_advantage.notifications.ussd.managers.segment_manager import (
    SegmentManager,
)


class RegistrationHandler(USSDHandler):
    """Handler for Uzazi Salama specific USSD logic."""

    def handle_state(
        self, state: str, session: Dict[str, Any], phone_number: str, ussd_code: str
    ) -> str:
        """Handle state-specific logic for Uzazi Salama."""
        state_handlers = {
            "CHECK_PATIENT_EXISTENCE": self._check_patient_existence,
            "VIEW_DETAILS": self._handle_view_details,
            "CONFIRM_OPT_OUT": self._handle_opt_out,
            "LIST_SEGMENTS": self._list_segments,
            "CONFIRM_ENROLLMENT": self._confirm_enrollment,
            "ENROLL_TO_SEGMENT": self._enroll_to_segment,
            "SELECT_REGION": self._list_regions,
            "CONFIRM_REGISTRATION": self._handle_confirm_registration,
            "REGISTRATION_SUCCESSFUL": self._handle_registration_successful,
        }

        handler = state_handlers.get(
            state,
            lambda s, p, u: self.state_machine.messages[session.get("language", "en")][
                state
            ],
        )
        return handler(session, phone_number, ussd_code)

    def _check_patient_existence(
        self, session: Dict[str, Any], phone_number: str, ussd_code: str
    ) -> str:
        """Check if the patient exists and return the appropriate state message."""
        patient_details = PatientManager.check_patient_exists(phone_number, ussd_code)
        if patient_details:
            session["patient_details"] = patient_details
            next_state = "EXISTING_PATIENT_MENU"
        else:
            next_state = "MAIN_MENU"
        session["state"] = next_state
        self.session_manager.save_session(session["session_id"], session)
        return self.state_machine.messages[session.get("language", "en")][next_state]

    def _handle_view_details(
        self, session: Dict[str, Any], phone_number: str, ussd_code: str
    ) -> str:
        """Handle viewing patient details."""
        patient_details = session.get("patient_details")
        person = patient_details.person  # type: ignore
        first_name = person.first_name
        last_name = person.last_name
        date_of_birth = str(person.date_of_birth)
        gender = person.gender
        language = session.get("language", "en")
        details_message_template = self.state_machine.messages[language].get(
            "VIEW_DETAILS", ""
        )
        return (
            details_message_template.replace("{first_name}", first_name)
            .replace("{last_name}", last_name)
            .replace("{date_of_birth}", date_of_birth)
            .replace("{gender}", gender)
            .replace("{phone_number}", phone_number)
        )

    def _get_selected_item(self, user_input: str, items: list) -> Any:
        """Helper method to get the selected item from a list based on user input."""
        try:
            selected_index = int(user_input) - 1
        except ValueError:
            selected_index = -1
        return items[selected_index] if 0 <= selected_index < len(items) else None

    def _confirm_enrollment(
        self, session: Dict[str, Any], phone_number: str, ussd_code: str
    ) -> str:
        """Handle confirming segment enrollment."""
        user_input = session.get("LIST_SEGMENTS", "")
        segments = session.get("segments", [])
        validation_result = self.validator.validate(
            "CONFIRM_ENROLLMENT", user_input or "", segments
        )  # type: ignore

        if not validation_result["is_valid"]:
            return validation_result["message"]  # type: ignore

        # If the input is valid, proceed with enrollment
        selected_segment = self._get_selected_item(str(user_input), segments)
        session["selected_segment"] = selected_segment
        self.session_manager.save_session(session["session_id"], session)

        return self.state_machine.messages[session.get("language", "en")][
            "CONFIRM_ENROLLMENT"
        ].format(segment=selected_segment)

    def _list_segments(
        self, session: Dict[str, Any], phone_number: str, ussd_code: str
    ) -> str:
        """Handle listing available segments for enrollment."""
        person = session.get("patient_details").person  # type: ignore
        segments = SegmentManager.get_available_segments_for_person(person)

        if not segments:
            return "END No available programs to enroll in."

        output = "\n".join(f"{i+1}. {segment}" for i, segment in enumerate(segments))
        session["segments"] = segments
        self.session_manager.save_session(session["session_id"], session)
        list_message_template = self.state_machine.messages[
            session.get("language", "en")
        ].get("LIST_SEGMENTS", "")
        return list_message_template.format(segments=output)

    def _enroll_to_segment(
        self, session: Dict[str, Any], phone_number: str, ussd_code: str
    ) -> str:
        """Handle the actual enrollment to the segment."""
        selected_segment = session.get("selected_segment", "")
        person = session.get("patient_details").person  # type: ignore
        success = SegmentManager.add_person_to_segment(
            person,
            selected_segment,
        )  # type: ignore
        if success:
            return self.state_machine.messages[session.get("language", "en")][
                "ENROLLMENT_SUCCESSFUL"
            ]
        else:
            return self.state_machine.messages[session.get("language", "en")][
                "ENROLLMENT_FAILED"
            ]

    def _handle_opt_out(
        self, session: Dict[str, Any], phone_number: str, ussd_code: str
    ) -> str:
        """Handle the opt-out confirmation."""
        patient_details = session.get("patient_details")
        person = patient_details.person  # type: ignore
        success = PatientManager.opt_out_patient(person)
        if success:
            return self.state_machine.messages[session.get("language", "en")][
                "OPT_OUT_SUCCESSFUL"
            ]
        else:
            return self.state_machine.messages[session.get("language", "en")][
                "OPT_OUT_FAILED"
            ]

    def _map_gender(self, gender_code: str, language: str) -> str:
        """Map the gender code to the full gender name based on the language."""
        if language == "sw":
            gender_dict = GENDER_DICT_SWAHILI
        else:
            gender_dict = GENDER_DICT

        return gender_dict.get(gender_code, "Unknown").capitalize()

    def _extract_patient_data(self, session: Dict[str, Any]) -> Dict[str, str]:
        """Extract patient data from session."""
        full_name = session.get("ENTER_NAME", "").strip()
        first_name, last_name = (
            full_name.split(" ", 1) if " " in full_name else (full_name, "")
        )
        date_of_birth = session.get("ENTER_DOB", "")
        consent = CONSENT_DICT.get(session.get("CONSENT_SMS", ""), "REJECTED")
        gender = session.get("ENTER_GENDER", "")
        region_name = session.get("SELECT_REGION", "")
        regions = session.get("regions", [])
        language = session.get("language", "")

        selected_region = self._get_selected_item(str(region_name), regions)

        return {
            "first_name": first_name,
            "last_name": last_name,
            "date_of_birth": date_of_birth,
            "gender": gender,
            "consent_status": consent,
            "region_name": selected_region,
            "language": language,
        }

    def _list_regions(
        self, session: Dict[str, Any], phone_number: str, ussd_code: str
    ) -> str:
        """List available regions."""
        region_names = RegionManager.get_operating_regions(ussd_code)
        if not region_names:
            session["state"] = "ENTER_NAME"
            self.session_manager.save_session(session["session_id"], session)
            return self.state_machine.messages[session.get("language", "en")].get(
                "ENTER_NAME", ""
            )
        output = "\n".join(f"{i+1}. {region}" for i, region in enumerate(region_names))
        session["regions"] = region_names
        self.session_manager.save_session(session["session_id"], session)
        list_message_template = self.state_machine.messages[
            session.get("language", "en")
        ].get("SELECT_REGION", "")
        return list_message_template.format(regions=output)

    def _handle_confirm_registration(
        self, session: Dict[str, Any], phone_number: str, ussd_code: str
    ) -> str:
        """Prepare and return confirmation message."""
        patient_data = self._extract_patient_data(session)
        language = session.get("language", "en")
        gender_code = patient_data.get("gender", "0")
        gender = self._map_gender(gender_code, language)
        confirmation_message_template = self.state_machine.messages[
            session.get("language", "en")
        ].get("CONFIRM_REGISTRATION", "")
        return (
            confirmation_message_template.replace(
                "{name}", f"{patient_data['first_name']} {patient_data['last_name']}"
            )
            .replace("{dob}", patient_data["date_of_birth"])
            .replace("{gender}", gender)
            .replace("{consent}", patient_data["consent_status"])
        )

    def _handle_registration_successful(
        self, session: Dict[str, Any], phone_number: str, ussd_code: str
    ) -> str:
        """Handle successful registration state."""
        patient_data = self._extract_patient_data(session)
        success = PatientManager.create_patient(
            first_name=patient_data["first_name"],
            last_name=patient_data["last_name"],
            date_of_birth=patient_data["date_of_birth"],
            gender=patient_data["gender"],
            phone_number=phone_number,
            consent_status=patient_data["consent_status"],
            ussd_code=ussd_code,
            associated_region=patient_data["region_name"],
            language=patient_data["language"],
        )
        return (
            self.state_machine.messages[session.get("language", "en")][
                "REGISTRATION_SUCCESSFUL"
            ]
            if success
            else self.state_machine.messages[session.get("language", "en")][
                "REGISTRATION_FAILED"
            ]
        )

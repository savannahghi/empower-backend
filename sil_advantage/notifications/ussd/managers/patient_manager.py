"""Handles ussd patient functionalities.

Classes:
    PatientManager: Provides methods to create persons and add
    new patients.
"""
import logging
from datetime import datetime
from typing import Any, Optional

from django.db import transaction
from django.db.models import Prefetch

from sil_advantage.common.models import Consent, Person, PersonContact
from sil_advantage.common.models.common_models import OperatingRegion
from sil_advantage.notifications.models import USSDCode
from sil_advantage.notifications.ussd import GENDER_DICT
from sil_advantage.notifications.ussd.managers.common_manager import (
    CommonFieldsManager,
)
from sil_advantage.patients.models import Patient

logger = logging.getLogger(__name__)


class PatientManager:
    """Provides methods to create persons and add new patients."""

    def __init__(self, code: Any):
        """Initialize."""
        self.common_fields_manager = CommonFieldsManager(code)
        self.common_fields = self.common_fields_manager.get_common_fields()

    @staticmethod
    def create_person(
        first_name: str,
        last_name: str,
        date_of_birth: str,
        gender: str,
        phone_number: str,
        consent_status: str,
        code: Any,
        associated_region: str,
        language: str,
    ) -> Person:
        """Create a new person with the provided details.

        Args:
            first_name (str): The first name of the person.
            last_name (str): The last name of the person.
            date_of_birth (str): The date of birth of the person in 'dd/mm/yyyy' format.
            gender (str): The gender of the person ('1' for Male, otherwise Female).
            phone_number (str): The phone number of the person.
            consent_status (str): Whether the person has confirmed consent for SMS
            contact.
            code (Any): The USSD code used for self-enrollment.
            associated_region (str): The region of the person.
            language (str): Preferred language of the person.

        Returns:
            person object: if the person is created successfully
        """
        dob = datetime.strptime(date_of_birth, "%d/%m/%Y").date()
        selected_gender = GENDER_DICT.get(gender)
        manager = PatientManager(code)

        try:
            if associated_region:
                region = OperatingRegion.objects.get(name=associated_region)
            else:
                region = None
            # Add person details.
            person = Person(
                first_name=first_name,
                last_name=last_name,
                date_of_birth=dob,
                gender=selected_gender,
                associated_region=region,
                language=language,
                **manager.common_fields,
            )
            person.save()

            # Add person contact details.
            PatientManager.add_person_contact_details(
                person, phone_number, consent_status, code
            )

            # Add person consent details.
            PatientManager.add_person_consent_details(person, consent_status, code)
            return person
        except Exception as e:
            logger.error(f"Error creating Person: {e}")
            raise RuntimeError(f"Error creating Person: {e}")

    @staticmethod
    def add_person_contact_details(
        person: Person, phone_number: str, consent_status: str, code: Any
    ) -> None:
        """Add person contact details."""
        manager = PatientManager(code)
        consent_given = {
            "VERIFIED": True,
            "REJECTED": False,
        }

        person_contact = PersonContact(
            person=person,
            contact_type="phone_number",
            contact=phone_number,
            consent_to_contact_given=consent_given.get(consent_status),
            is_primary_contact=True,
            **manager.common_fields,
        )
        person_contact.save()

    @staticmethod
    def add_person_consent_details(
        person: Person, consent_status: str, code: Any
    ) -> None:
        """Add person consent details."""
        manager = PatientManager(code)

        consent = Consent(
            person=person,
            consent_type="SMS_HEALTH_EDUCATION",
            status=consent_status,
            verification_type="USSD",
            **manager.common_fields,
        )
        consent.save()

    @staticmethod
    def create_patient(
        first_name: str,
        last_name: str,
        date_of_birth: str,
        gender: str,
        phone_number: str,
        consent_status: str,
        ussd_code: str,
        associated_region: str,
        language: str,
    ) -> bool:
        """Create a new patient with the provided details.

        Args:
            first_name (str): The first name of the patient.
            last_name (str): The last name of the patient.
            date_of_birth (str): The date of birth of the patient in 'dd/mm/yyyy'
                format.
            gender (str): The gender of the patient ('1' for Male, otherwise
                Female).
            phone_number (str): The phone number of the patient.
            consent_status (str): Whether the patient has confirmed consent for SMS
            contact.
            ussd_code (str): The USSD code used for self-enrollment.
            associated_region (str): The region of the patient.
            language (str): Preferred language of the patient.

        Returns:
            bool: True if the patient is created successfully, False otherwise.
        """
        try:
            code = USSDCode.objects.get(ussd_code=ussd_code)
            manager = PatientManager(code)

            person = PatientManager.create_person(
                first_name,
                last_name,
                date_of_birth,
                gender,
                phone_number,
                consent_status,
                code,
                associated_region,
                language,
            )

            patient = Patient(
                person=person,
                source="USSD_SELF_ENROLLMENT",
                **manager.common_fields,
            )
            patient.save()
            return True
        except Exception as e:
            logger.error(f"Error creating patient: {e}")
            raise RuntimeError(f"Error creating patient: {e}")

    @staticmethod
    def opt_out_patient(person: Person) -> bool:
        """Deactivate the patient once opted out."""
        try:
            patient = (
                Patient.objects.select_related("person")
                .prefetch_related(Prefetch("person__person_contacts"))
                .get(person=person, organisation=person.organisation, active=True)
            )
            person_contact = patient.person.person_contacts.first()

            patient.active = False
            patient.person.active = False
            person_contact.consent_to_contact_given = False  # type: ignore

            with transaction.atomic():
                patient.save()
                patient.person.save()
                person_contact.save()  # type: ignore
            return True
        except Exception as e:
            logger.error(f"An error occurred while opting out the patient: {e}")
            return False

    @staticmethod
    def opt_out_person(person: Person) -> None:
        """Deactivate the person once opted out."""
        try:
            person.active = False
            person_contact = person.person_contacts.first()
            person_contact.consent_to_contact_given = False  # type: ignore

            with transaction.atomic():
                person.save()
                person_contact.save()  # type: ignore
        except Exception as e:
            logger.error(f"An error occurred while opting out the person: {e}")
            raise RuntimeError(f"An error occurred while opting out the person: {e}")

    @staticmethod
    def check_person_exists(phone_number: str, ussd_code: str) -> Optional[Person]:
        """Check if the person exists in the database."""
        try:
            code = USSDCode.objects.get(ussd_code=ussd_code)
            person = Person.objects.filter(
                person_contacts__contact=phone_number,
                organisation=code.organisation,
                active=True,
            ).last()
            return person
        except Exception as e:
            logger.error(f"Error fetching person: {e}")
            raise RuntimeError(f"Error fetching person: {e}")

    @staticmethod
    def check_patient_exists(phone_number: str, ussd_code: str) -> Optional[Patient]:
        """Check if the patient exists in the database."""
        try:
            code = USSDCode.objects.get(ussd_code=ussd_code)
            patient = Patient.objects.filter(
                person__person_contacts__contact=phone_number,
                organisation=code.organisation,
                active=True,
            ).last()
            return patient
        except Exception as e:
            logger.error(f"Error fetching patient: {e}")
            raise RuntimeError(f"Error fetching patient: {e}")

"""Patients settings."""
from typing import List

from django.conf import settings

from sil_advantage.settings.manager import SettingManager

DEFAULT_SMS_TEMPLATES = settings.DEFAULT_SMS_INTENTION_TEMPLATES  # type: ignore


BRANCH_PATIENTS_SETTINGS: List[SettingManager] = [
    SettingManager(
        "sms:patient_communication_consent_otp_en_template",
        "Patient Communication Consent OTP English Template",
        DEFAULT_SMS_TEMPLATES["PATIENT_COMMUNICATION_CONSENT_OTP"],
        str,
        None,
    ),
]
ORG_PATIENTS_SETTINGS = [
    SettingManager(
        "patients:patient_id_format",
        "Patient ID Format",
        "{file_number}",
        str,
        lambda x: "file_number" in x,
    ),
    SettingManager(
        "patients:patient_full_name",
        "Patient's middle name is required?",
        True,
        bool,
    ),
    SettingManager(
        "patients:patient_registration_sms",
        "Send a registration message to a patient?",
        True,
        bool,
    ),
    SettingManager(
        "patients:patient_global_health_id",
        "Send Slade's unique global health ID?",
        False,
        bool,
    ),
    SettingManager(
        "sms:patient_communication_consent_otp_en_template",
        "Patient Communication Consent OTP English Template",
        DEFAULT_SMS_TEMPLATES["PATIENT_COMMUNICATION_CONSENT_OTP"],
        str,
        None,
    ),
]

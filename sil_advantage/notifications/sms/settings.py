"""SMS settings."""
from typing import List

from django.conf import settings

from sil_advantage.settings.manager import SettingManager

DEFAULT_SMS_TEMPLATES = settings.DEFAULT_SMS_INTENTION_TEMPLATES  # type: ignore


BRANCH_SMS_SETTINGS: List[SettingManager] = [
    SettingManager(
        "sms:appointment_creation_en_template",
        "Appointment Creation English Template",
        DEFAULT_SMS_TEMPLATES["APPOINTMENT_CREATION"],
        str,
        None,
    ),
    SettingManager(
        "sms:appointment_reminder_en_template",
        "Appointment Reminder English Template",
        DEFAULT_SMS_TEMPLATES["APPOINTMENT_REMINDER"],
        str,
        None,
    ),
    SettingManager(
        "sms:appointment_reschedule_en_template",
        "Appointment Rescheduling English Template",
        DEFAULT_SMS_TEMPLATES["APPOINTMENT_RESCHEDULE"],
        str,
        None,
    ),
    SettingManager(
        "sms:appointment_cancellation_en_template",
        "Appointment Cancellation English Template",
        DEFAULT_SMS_TEMPLATES["APPOINTMENT_CANCELLATION"],
        str,
        None,
    ),
    SettingManager(
        "sms:check_in_creation_en_template",
        "Check-in Creation English Template",
        DEFAULT_SMS_TEMPLATES["CHECK_IN_CREATION"],
        str,
        None,
    ),
    SettingManager(
        "sms:patient_global_health_id_en_template",
        "Patient Global Health ID English Template",
        DEFAULT_SMS_TEMPLATES["PATIENT_GLOBAL_HEALTH_ID"],
        str,
        None,
    ),
    SettingManager(
        "sms:patient_registration_en_template",
        "Patient Registration English Template",
        DEFAULT_SMS_TEMPLATES["PATIENT_REGISTRATION_EN"],
        str,
        None,
    ),
    SettingManager(
        "sms:patient_registration_sw_template",
        "Patient Registration Swahili Template",
        DEFAULT_SMS_TEMPLATES["PATIENT_REGISTRATION_SW"],
        str,
        None,
    ),
    SettingManager(
        "sms:visit_summary_en_template",
        "Visit Summary English Template",
        DEFAULT_SMS_TEMPLATES["VISIT_SUMMARY"],
        str,
        None,
    ),
]
ORG_SMS_SETTINGS = [
    SettingManager(
        "sms:appointment_creation_en_template",
        "Appointment Creation English Template",
        DEFAULT_SMS_TEMPLATES["APPOINTMENT_CREATION"],
        str,
        None,
    ),
    SettingManager(
        "sms:appointment_reminder_en_template",
        "Appointment Reminder English Template",
        DEFAULT_SMS_TEMPLATES["APPOINTMENT_REMINDER"],
        str,
        None,
    ),
    SettingManager(
        "sms:appointment_reschedule_en_template",
        "Appointment Rescheduling English Template",
        DEFAULT_SMS_TEMPLATES["APPOINTMENT_RESCHEDULE"],
        str,
        None,
    ),
    SettingManager(
        "sms:appointment_cancellation_en_template",
        "Appointment Cancellation English Template",
        DEFAULT_SMS_TEMPLATES["APPOINTMENT_CANCELLATION"],
        str,
        None,
    ),
    SettingManager(
        "sms:check_in_creation_en_template",
        "Check-in Creation English Template",
        DEFAULT_SMS_TEMPLATES["CHECK_IN_CREATION"],
        str,
        None,
    ),
    SettingManager(
        "sms:post_visit_survey_en_template",
        "Post Visit Survey English Template",
        DEFAULT_SMS_TEMPLATES["POST_VISIT_SURVEY"],
        str,
        None,
    ),
    SettingManager(
        "sms:visit_summary_en_template",
        "Visit Summary English Template",
        DEFAULT_SMS_TEMPLATES["VISIT_SUMMARY"],
        str,
        None,
    ),
    SettingManager(
        "sms:patient_registration_en_template",
        "Patient Registration English Template",
        DEFAULT_SMS_TEMPLATES["PATIENT_REGISTRATION_EN"],
        str,
        None,
    ),
    SettingManager(
        "sms:patient_registration_sw_template",
        "Patient Registration English Template",
        DEFAULT_SMS_TEMPLATES["PATIENT_REGISTRATION_SW"],
        str,
        None,
    ),
    SettingManager(
        "sms:practitioner_daily_digest_en_template",
        "Practitioner Daily Digest English Template",
        DEFAULT_SMS_TEMPLATES["PRACTITIONER_DAILY_DIGEST"],
        str,
        None,
    ),
    SettingManager(
        "sms:patient_global_health_id_en_template",
        "Patient Global Health ID English Template",
        DEFAULT_SMS_TEMPLATES["PATIENT_GLOBAL_HEALTH_ID"],
        str,
        None,
    ),
]

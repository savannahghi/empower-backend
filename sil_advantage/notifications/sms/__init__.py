"""SMS."""

TRANSACTIONAL_SMS_INTENTIONS = (
    ("APPOINTMENT_CREATION", "Appointment Creation"),
    ("APPOINTMENT_REMINDER", "Appointment Reminder"),
    ("APPOINTMENT_RESCHEDULE", "Appointment Reschedule"),
    ("APPOINTMENT_CANCELLATION", "Appointment Cancellation"),
    ("CHECK_IN_CREATION", "Check-in Creation"),
    ("PATIENT_REGISTRATION", "Patient Registration"),
    ("DIRECT_MESSAGE", "Direct Message"),
    ("PRACTITIONER_DAILY_DIGEST", "Practitioner Daily Digest"),
    ("VISIT_SUMMARY", "Visit Summary"),
    ("OTP", "SMS One Time Password"),
    ("PATIENT_GLOBAL_HEALTH_ID", "Patient Global Health ID"),
    ("PATIENT_COMMUNICATION_CONSENT_OTP", "Communication Consent One Time Password"),
)
PROMOTIONAL_SMS_INTENTIONS = (
    ("POST_VISIT_SURVEY", "Post Visit Survey"),
    ("BROADCAST", "Broadcast"),
)
SMS_INTENTIONS = TRANSACTIONAL_SMS_INTENTIONS + PROMOTIONAL_SMS_INTENTIONS

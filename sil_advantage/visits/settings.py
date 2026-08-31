"""Visits settings."""
from typing import List

from django.conf import settings

from sil_advantage.settings.manager import SettingManager

DEFAULT_SMS_TEMPLATES = settings.DEFAULT_SMS_INTENTION_TEMPLATES  # type: ignore


BRANCH_VISITS_SETTINGS: List[SettingManager] = []
ORG_VISITS_SETTINGS = [
    SettingManager(
        "visits:visit_number_format",
        "Visit Number Format",
        "{seq_number:04d}/{created:%y}",
        str,
        lambda x: "seq_number" in x,
    ),
    SettingManager(
        "visit:document_number_format",
        "Visit Document Number Format",
        "{custom_input}/{org}/{branch}/{year}/{seq}",
        str,
        bool,
    ),
    SettingManager(
        "visits:post_visit_surveys_enabled",
        "Send Post Visit Surveys?",
        True,
        bool,
    ),
    SettingManager(
        "visits:post_visit_survey_template",
        "Post Visit Survey Form",
        # Formly JSON Schema
        [
            {
                "type": "buttongroup",
                "key": "facility_services_rating",
                "props": {
                    "label": (
                        "How would you rate the "
                        "medical services provided at this facility?"
                    ),
                    "helpText": "1 being worst, 5 being best",
                    "buttons": [
                        {"display": "1", "value": "1"},
                        {"display": "2", "value": "2"},
                        {"display": "3", "value": "3"},
                        {"display": "4", "value": "4"},
                        {"display": "5", "value": "5"},
                    ],
                    "required": True,
                },
            },
            {
                "type": "buttongroup",
                "key": "staff_rating",
                "props": {
                    "label": (
                        "How would you rate the staff that "
                        "assisted you during the visit?"
                    ),
                    "helpText": "1 being worst, 5 being best",
                    "buttons": [
                        {"display": "1", "value": "1"},
                        {"display": "2", "value": "2"},
                        {"display": "3", "value": "3"},
                        {"display": "4", "value": "4"},
                        {"display": "5", "value": "5"},
                    ],
                    "required": True,
                },
            },
            {
                "type": "buttongroup",
                "key": "appointment_booking_rating",
                "props": {
                    "label": (
                        "If you booked an appointment, "
                        "how would you rate your appointment booking experience?"
                    ),
                    "helpText": "1 being lowest, 5 being highest",
                    "buttons": [
                        {"display": "1", "value": "1"},
                        {"display": "2", "value": "2"},
                        {"display": "3", "value": "3"},
                        {"display": "4", "value": "4"},
                        {"display": "5", "value": "5"},
                    ],
                    "required": False,
                },
            },
            {
                "type": "buttongroup",
                "key": "would_recommend_rating",
                "props": {
                    "label": (
                        "How likely are you to recommend the facility "
                        "to a friend or family member?"
                    ),
                    "helpText": '1 being "not likely", 5 being "very likely"',
                    "buttons": [
                        {"display": "1", "value": "1"},
                        {"display": "2", "value": "2"},
                        {"display": "3", "value": "3"},
                        {"display": "4", "value": "4"},
                        {"display": "5", "value": "5"},
                    ],
                    "required": True,
                },
            },
            {
                "type": "textarea",
                "key": "improvements_long_form",
                "props": {
                    "label": (
                        "Is there anything that could have been "
                        "done better during your visit?"
                    ),
                    "required": False,
                },
            },
        ],
        list,
    ),
]

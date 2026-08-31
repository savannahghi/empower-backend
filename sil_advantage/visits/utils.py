"""Visits utilities."""
from dataclasses import dataclass
from typing import Any, Optional

from django.conf import settings
from sil_shlink import ShlinkPayload

from sil_advantage.common.models import Person
from sil_advantage.common.utilities import generate_token
from sil_advantage.common.utilities.urlshortener import shlink_shorten_url
from sil_advantage.notifications.sms.utils import send_custom_sms
from sil_advantage.visits import SHORTCUTS
from sil_advantage.visits.models import Visit

"""Vitals."""


@dataclass
class ReferenceRange:
    """Hold information about a particular range for a vital.

    https://build.fhir.org/valueset-referencerange-meaning.html
    """

    # ranges are start inclusive & end exclusive
    start: int | float
    end: int | float
    uk_news_score: Optional[int]
    display: str


# National Early Warning Score
UK_NEWS_THRESHOLDS: dict[str, tuple[ReferenceRange, ...]] = {
    "RESPIRATION_RATE": (
        ReferenceRange(1, 9, 3, "Very Low"),
        ReferenceRange(9, 12, 1, "Low"),
        ReferenceRange(12, 21, 0, "Normal"),
        ReferenceRange(21, 25, 2, "High"),
        ReferenceRange(25, 201, 3, "Very High"),
    ),
    # Arterial Blood Oxygen Saturation as measured from
    # a peripheral oximeter.
    # Ranges are for SpO2 Scale 1
    # Units: %
    "SPO2": (
        ReferenceRange(1, 92, 3, "Critical"),
        ReferenceRange(92, 94, 2, "Decreased"),
        ReferenceRange(94, 96, 1, "Decreased"),
        ReferenceRange(96, 101, 0, "Normal"),
    ),
    # Systolic Blood Pressure
    # Taken with a manual cuff in either a sitting or standing position
    "SYSTOLIC_BLOOD_PRESSURE": (
        ReferenceRange(1, 91, 3, "Low"),
        ReferenceRange(91, 101, 2, "Normal"),
        ReferenceRange(101, 111, 1, "Normal"),
        ReferenceRange(111, 120, 0, "Normal"),
        ReferenceRange(120, 130, 0, "Elevated"),
        ReferenceRange(130, 140, 0, "High BP Stage 1"),
        ReferenceRange(140, 180, 0, "High BP Stage 2"),
        ReferenceRange(180, 220, 0, "Hypertensive Crisis"),
        ReferenceRange(220, 301, 3, "Hypertensive Crisis"),
    ),
    "PULSE_RATE": (
        ReferenceRange(10, 41, 3, "Very Low"),
        ReferenceRange(41, 51, 1, "Low"),
        ReferenceRange(51, 91, 0, "Normal"),
        ReferenceRange(91, 111, 1, "High"),
        ReferenceRange(111, 131, 2, "Very High"),
        ReferenceRange(131, 201, 3, "Very High"),
    ),
    # Temperature
    # Units: Degrees Centigrade
    "TEMPERATURE": (
        ReferenceRange(10.0, 35.1, 3, "Very Low"),
        ReferenceRange(35.1, 36.1, 1, "Low"),
        ReferenceRange(36.1, 38.1, 0, "Normal"),
        ReferenceRange(38.1, 39.1, 1, "High"),
        ReferenceRange(39.1, 50.1, 2, "Very High"),
    ),
}

VITALS_REFERENCE_RANGES: dict[str, tuple[ReferenceRange, ...]] = {
    **UK_NEWS_THRESHOLDS,
    # Body Mass Index (BMI) is a relationship between weight and height
    # that is associated with body fat and health risk.
    # Units: kg/m2
    "BMI": (
        ReferenceRange(1.0, 16.0, None, "Severe Thinness"),
        ReferenceRange(16.0, 17.0, None, "Moderate Thinness"),
        ReferenceRange(17.0, 18.5, None, "Mild Thinness"),
        ReferenceRange(18.5, 25.0, None, "Normal"),
        ReferenceRange(25.0, 30.0, None, "Overweight"),
        ReferenceRange(30.0, 35.0, None, "Obese Class I"),
        ReferenceRange(35.0, 40.0, None, "Obese Class II"),
        ReferenceRange(40.0, 200.0, None, "Obese Class III"),
    ),
    # Mid-upper arm circumference
    # MUAC is the circumference of the left upper arm,
    # measured at the mid-point between the tip of the shoulder
    # and the tip of the elbow.
    # MUAC is useful for the assessment of nutritional status.
    # Units: Centimeters
    "MUAC": (
        ReferenceRange(0.0, 11.0, None, "Severe Acute Malnutrition"),
        ReferenceRange(11.0, 12.5, None, "Moderate Acute Malnutrition"),
        ReferenceRange(12.5, 13.5, None, "Growth Promotion and Monitoring"),
        ReferenceRange(13.5, 25.1, None, "Normal"),
    ),
    # Diastolic Blood Pressure
    "DIASTOLIC_BLOOD_PRESSURE": (
        ReferenceRange(1, 80, None, "Normal"),
        ReferenceRange(80, 90, None, "High BP Stage 1"),
        ReferenceRange(90, 120, None, "High BP Stage 2"),
        ReferenceRange(120, 301, None, "Hypertensive Crisis"),
    ),
    # Preprandial Blood Sugar
    # Units: mmol/l
    "PREPRANDIAL_BLOOD_SUGAR": (
        ReferenceRange(1.0, 5.5, None, "Normal"),
        ReferenceRange(5.5, 7.0, None, "Prediabetes"),
        ReferenceRange(7.0, 20.0, None, "Diabetes"),
    ),
    # Postprandial Blood Sugar
    # 2 hours post-prandial
    # Units: mmol/l
    "POSTPRANDIAL_BLOOD_SUGAR": (
        ReferenceRange(1.0, 7.8, None, "Normal"),
        ReferenceRange(7.8, 11.0, None, "Prediabetes"),
        ReferenceRange(11.0, 20.0, None, "Diabetes"),
    ),
}

"""SMS."""


def send_post_visit_survey_sms(visit: Visit) -> None:
    """Send a post visit survey sms."""
    token = generate_token(8)
    visit.post_visit_survey_token = token
    visit.save(update_fields=["post_visit_survey_token"])

    long_url = settings.ADVANTAGE_FRONTEND_URL + f"/survey?t={token}"
    priority = settings.CELERY_TASK_LOW_PRIORITY

    person: Person = visit.patient.person
    phone_number = person.phone_number
    org = visit.organisation
    branch_id = visit.branch_id
    assert phone_number is not None

    payload = ShlinkPayload(
        long_url=long_url,
        domain=settings.SIL_SHLINK["SHLINK_CUSTOM_DOMAIN"],
    )
    short_url = shlink_shorten_url(payload=payload)
    send_custom_sms(
        "POST_VISIT_SURVEY",
        phone_number,
        org,
        branch_id,
        person,
        priority,
        date=visit.start.strftime("%a %b-%d"),
        link=short_url,
        department_id=visit.department_id,
        workstation_id=visit.workstation_id,
    )


def send_visit_summary_sms(visit: Visit) -> None:
    """Send a post visit summary sms."""
    person: Person = visit.patient.person
    phone_number = person.phone_number
    if not phone_number:
        return

    token = visit.post_visit_survey_token
    if not token:
        token = generate_token(8)
        visit.post_visit_survey_token = token
        visit.save(update_fields=["post_visit_survey_token"])

    long_url = settings.ADVANTAGE_FRONTEND_URL + f"/summary?t={token}"

    priority = settings.CELERY_TASK_LOW_PRIORITY

    org = visit.organisation
    branch_id = visit.branch_id
    payload = ShlinkPayload(
        long_url=long_url,
        domain=settings.SIL_SHLINK["SHLINK_CUSTOM_DOMAIN"],
    )
    short_url = shlink_shorten_url(payload=payload)

    send_custom_sms(
        "VISIT_SUMMARY",
        phone_number,
        org,
        branch_id,
        person,
        priority,
        date=visit.start.strftime("%a %b-%d"),
        link=short_url,
        org_phone_number=org.phone_number,
        department_id=visit.department_id,
        workstation_id=visit.workstation_id,
    )


def generate_document_number(
    setting: str,
    document_prefix: str,
    organisation_name: str,
    branch_name: str,
    year: int,
    seq: str,
) -> str:
    """Generate a document number following a specific format.

    Returns:
        str: The generated document number.

    """
    custom_input = document_prefix.upper()
    org = organisation_name[:3].upper()
    branch = branch_name[:3].upper()
    seq = str(seq).zfill(4)
    default_keys = ["custom_input", "org", "branch", "year", "seq"]
    document_number_template = setting.split("/")
    provided_parts = [part.strip("{}").strip() for part in document_number_template]

    for part in provided_parts:
        if part not in default_keys:
            custom_input = part.upper()
            index = provided_parts.index(part.strip("{}").strip())
            provided_parts[index] = "custom_input"

    doc_format = "/".join(f"{{{item}}}" for item in provided_parts if item)
    document_number = doc_format.format(
        custom_input=custom_input,
        org=org,
        branch=branch,
        year=year,
        seq=seq,
    )
    return document_number


def update_state_transition(obj: Any, target_state: str) -> None:
    """Apply workflow state shortcut transitions to the object."""
    for state in SHORTCUTS[target_state]:
        obj.workflow_state = state
        obj.save(update_fields=["workflow_state"])

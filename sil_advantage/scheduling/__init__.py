"""Scheduling app."""


class SLOT_STATUS:
    """Status a slot can be in."""

    BUSY = "BUSY"
    FREE = "FREE"
    BUSY_TENTATIVE = "BUSY_TENTATIVE"
    BUSY_UNAVAILABLE = "BUSY_UNAVAILABLE"

    CHOICES = [
        (
            BUSY,
            "Indicates that the time interval is busy because one "
            "or more events have been scheduled for that interval.",
        ),
        (FREE, "Indicates that the time interval is free for scheduling."),
        (
            BUSY_TENTATIVE,
            "Indicates that the time interval is busy because one "
            "or more events have been tentatively scheduled for that interval.",
        ),
        (
            BUSY_UNAVAILABLE,
            "Indicates that the time interval is busy and that the "
            "interval can not be scheduled.",
        ),
    ]


class APPOINTMENT_STATUS:
    """Status an appointment can be in."""

    BOOKED = "BOOKED"
    CANCELLED = "CANCELLED"
    FULFILLED = "FULFILLED"
    NO_SHOW = "NO_SHOW"
    PENDING = "PENDING"
    PROPOSED = "PROPOSED"
    ARRIVED = "ARRIVED"

    CHOICES = [
        (
            BOOKED,
            "All participant(s) have been considered and the appointment"
            " is confirmed to go ahead at the date/times specified.",
        ),
        (CANCELLED, "The appointment has been cancelled."),
        (
            FULFILLED,
            "This appointment has completed and may have resulted " "in an encounter.",
        ),
        (
            NO_SHOW,
            "Some or all of the participant(s) have not/did not appear for "
            "the appointment (usually the patient).",
        ),
        (
            PENDING,
            "Some or all of the participant(s) have not finalized their "
            "acceptance of the appointment request.",
        ),
        (
            PROPOSED,
            "None of the participant(s) have finalized their acceptance "
            "of the appointment request, and the start/end time may not be set yet.",
        ),
        (ARRIVED, "Some of the patients have arrived."),
    ]


# FHIR Appointment Type
# https://terminology.hl7.org/5.1.0/ValueSet-v2-0276.html
class APPOINTMENT_TYPE:
    """Type of appointment that can be selected."""

    CHECKUP = "CHECKUP"
    EMERGENCY = "EMERGENCY"
    FOLLOWUP = "FOLLOWUP"
    ROUTINE = "ROUTINE"
    WALKIN = "WALKIN"

    CHOICES = [
        (CHECKUP, "A routine check-up, such as an annual physical"),
        (EMERGENCY, "Emergency appointment"),
        (FOLLOWUP, "A follow up visit from a previous appointment"),
        (ROUTINE, "Routine appointment"),
        (WALKIN, "A previously unscheduled walk-in visit"),
    ]


# FHIR Appointment/Act Priority
# https://www.hl7.org/fhir/appointment-definitions.html#Appointment.priority
# http://terminology.hl7.org/CodeSystem/v3-ActPriority
class APPOINTMENT_PRIORITY:
    """Priority choices to select when setting up an appointment."""

    ASAP = "ASAP"
    EMERGENCY = "EMERGENCY"
    PREOP = "PREOP"
    ROUTINE = "ROUTINE"

    CHOICES = [
        (ASAP, "As soon as possible, next highest priority after emergency"),
        (
            EMERGENCY,
            "An unforeseen combination of circumstances or the resulting state that "
            "calls for immediate action",
        ),
        (
            PREOP,
            "Indicates that a service is to be performed prior to a scheduled "
            "surgery. When ordering a service and using the pre-op priority, "
            "a check is done to see the amount of time that must be allowed "
            "for performance of the service.",
        ),
        (ROUTINE, "Routine service, do at usual work hours"),
    ]


class ACTOR_OPTIONS:
    """Actors that can be used to set up a schedule."""

    FACILITY = "FACILITY"
    HEALTHCARE_SERVICE = "HEALTHCARE_SERVICE"
    PRACTITIONER = "PRACTITIONER"

    CHOICES = [
        (FACILITY, "FACILITY"),
        (HEALTHCARE_SERVICE, "HEALTHCARE SERVICE"),
        (PRACTITIONER, "PRACTITIONER"),
    ]


SCHEDULE_ACTOR_CHOICES = (
    ("FACILITY", "FACILITY"),
    ("HEALTHCARE_SERVICE", "HEALTHCARE_SERVICE"),
    ("PRACTITIONER", "PRACTITIONER"),
)

PRACTITIONER_TYPES = (
    ("OPHTHALMOLOGY", "OPHTHALMOLOGY"),
    ("INTERNAL MEDICINE", "INTERNAL MEDICINE"),
    ("CLINICAL PATHOLOGY", "CLINICAL PATHOLOGY"),
    ("CONSERVATIVE DENTISTRY", "CONSERVATIVE DENTISTRY"),
    ("GENERAL SURGERY  PLASTIC SURGERY", "GENERAL SURGERY  PLASTIC SURGERY"),
    ("MICROBIOLOGY", "MICROBIOLOGY"),
    ("ORAL PATHOLOGY", "ORAL PATHOLOGY"),
    (
        "GENERAL SURGERY  PAEDIATRIC SURGERY",
        "GENERAL SURGERY  PAEDIATRIC SURGERY",
    ),
    (
        "OBSTETRICS AND GYNAECOLOGY  ONCOLOGY/RADIOTHERAPY",
        "OBSTETRICS AND GYNAECOLOGY  ONCOLOGY/RADIOTHERAPY",
    ),  # noqa
    ("ENDODONTICS", "ENDODONTICS"),
    ("RADIOLOGY", "RADIOLOGY"),
    ("NEPHROLOGY", "NEPHROLOGY"),
    ("EMERGENCY MEDICINE", "EMERGENCY MEDICINE"),
    (
        "EAR  NOSE AND THROAT (ENT SURGERY)",
        "EAR  NOSE AND THROAT (ENT SURGERY)",
    ),  # noqa
    ("PAEDIATRIC SURGERY", "PAEDIATRIC SURGERY"),
    ("ONCOLOGY", "ONCOLOGY"),
    ("PROSTHETIC DENTISTRY", "PROSTHETIC DENTISTRY"),
    ("OBSTETRICS AND GYNAECOLOGY", "OBSTETRICS AND GYNAECOLOGY"),
    ("PUBLIC HEALTH", "PUBLIC HEALTH"),
    ("OCCUPATIONAL MEDICINE", "OCCUPATIONAL MEDICINE"),
    ("GENERAL PATHOLOGY", "GENERAL PATHOLOGY"),
    ("NEUROSURGERY", "NEUROSURGERY"),
    ("DIABETOLOGY", "DIABETOLOGY"),
    ("CLINICAL MEDICAL GENETICS", "CLINICAL MEDICAL GENETICS"),
    ("GENERAL PRACTITIONER", "GENERAL PRACTITIONER"),
    ("NEUROLOGY", "NEUROLOGY"),
    ("PROSTHODONTICS", "PROSTHODONTICS"),
    ("DERMATOLOGY  INTERNAL MEDICINE", "DERMATOLOGY  INTERNAL MEDICINE"),
    ("ORTHOPAEDICS", "ORTHOPAEDICS"),
    ("BIOMATERIALS SCIENCE", "BIOMATERIALS SCIENCE"),
    ("ORTHOPAEDICS AND TRAUMA SURGERY", "ORTHOPAEDICS AND TRAUMA SURGERY"),
    ("RADIOTHERAPY", "RADIOTHERAPY"),
    ("PAEDIATRIC DENTISTRY", "PAEDIATRIC DENTISTRY"),
    (
        "INTERNAL MEDICINE  ONCOLOGY/RADIOTHERAPY",
        "INTERNAL MEDICINE  ONCOLOGY/RADIOTHERAPY",
    ),  # noqa
    ("ORTHODONTICS", "ORTHODONTICS"),
    ("RESTORATIVE DENTISTRY", "RESTORATIVE DENTISTRY"),
    ("GENERAL SURGERY", "GENERAL SURGERY"),
    ("ORAL AND MAXILLOFACIAL SURGERY", "ORAL AND MAXILLOFACIAL SURGERY"),
    ("DERMATOLOGY", "DERMATOLOGY"),
    ("PSYCHIATRY", "PSYCHIATRY"),
    ("GENERAL SURGERY  ORTHOPAEDICS", "GENERAL SURGERY  ORTHOPAEDICS"),
    ("DENTAL", "DENTAL"),
    ("ORTHOPAEDIC SURGERY", "ORTHOPAEDIC SURGERY"),
    ("DENTAL RADIOLOGY", "DENTAL RADIOLOGY"),
    ("PERIODONTOLOGY", "PERIODONTOLOGY"),
    ("FAMILY MEDICINE", "FAMILY MEDICINE"),
    ("PALLIATIVE MEDICINE", "PALLIATIVE MEDICINE"),
    ("PLASTIC SURGERY", "PLASTIC SURGERY"),
    ("PAEDIATRICS AND CHILD HEALTH", "PAEDIATRICS AND CHILD HEALTH"),
    ("ANAESTHESIA", "ANAESTHESIA"),
    ("CARDIOLOGIST", "CARDIOLOGIST"),
    ("UROLOGIST", "UROLOGIST"),
    ("PSYCHOLOGIST", "PSYCHOLOGIST"),
    ("PHYSIOTHERAPIST", "PHYSIOTHERAPIST"),
    ("FUNCTIONAL MEDICINE", "FUNCTIONAL MEDICINE"),
    ("CARDIOTHORACIC SURGEON", "CARDIOTHORACIC SURGEON"),
    ("HIV/AIDS SPECIALIST", "HIV/AIDS SPECIALIST"),
    ("FAMILY THERAPIST", "FAMILY THERAPIST"),
    ("PATHOLOGY", "PATHOLOGY"),
    ("NUTRITIONIST", "NUTRITIONIST"),
    ("PHYSICIAN", "PHYSICIAN"),
    ("MCH", "Mother and Child Health"),
    ("OTHER", "OTHER"),
)

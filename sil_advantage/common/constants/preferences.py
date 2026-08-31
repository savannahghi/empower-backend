"""Onboarding Preferences constants."""


class QUESTION_TYPES:
    """Question types."""

    TOPIC = "TOPIC"
    INTERESTS = "INTERESTS"
    OTHER = "OTHER"

    CHOICES = [
        (TOPIC, ("This is a question about topics.")),
        (INTERESTS, ("This is a question about interests.")),
        (OTHER, ("Other.")),
    ]


class QUESTION_STRUCTURE_TYPES:
    """Question structure types."""

    OPEN_ENDED = "OPEN_ENDED"
    SINGLE_CLOSE_ENDED = "SINGLE_CLOSE_ENDED"
    MULTICHOICE_CLOSE_ENDED = "MULTICHOICE_CLOSE_ENDED"

    CHOICES = [
        (OPEN_ENDED, ("The question is open ended and any answer is allowed.")),
        (
            SINGLE_CLOSE_ENDED,
            ("The question can only have a single answer in our provided choices."),
        ),
        (
            MULTICHOICE_CLOSE_ENDED,
            ("The question can have multiple answers from our choices."),
        ),
    ]


INTERESTS_QUESTIION = {
    "question_text": "How would you like to use AfyaMoja?",
    "choices": [
        {"1": "To manage bookings and appointments", "selected": False},
        {"2": "To communicate with my clients", "selected": False},
        {"3": "To post shifts", "selected": False},
        {"4": "To find open shifts", "selected": False},
    ],
    "question_type": QUESTION_TYPES.INTERESTS,
    "question_structure": QUESTION_STRUCTURE_TYPES.MULTICHOICE_CLOSE_ENDED,
}

TOPIC_QUESTION = (
    {
        "question_text": "Which of these topics would you be interested in?",
        "choices": [
            {"1": "Cancer", "selected": False},
            {"2": "Diabetes", "selected": False},
            {"3": "Hypertension", "selected": False},
            {"4": "Wellness and fitness", "selected": False},
            {"5": "ICD10", "selected": False},
            {"6": "Nutrionist", "selected": False},
        ],
        "question_type": QUESTION_TYPES.TOPIC,
        "question_structure": QUESTION_STRUCTURE_TYPES.MULTICHOICE_CLOSE_ENDED,
    },
)


ORGANISATION_ONBOARDING_PREFERENCES = [INTERESTS_QUESTIION, TOPIC_QUESTION]

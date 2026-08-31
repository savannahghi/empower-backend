"""USSD State Logic."""

STATE_DEFINITIONS = {
    "LANGUAGE_SELECTION": {
        "next_state": {
            "1": "CHECK_PATIENT_EXISTENCE",
            "2": "CHECK_PATIENT_EXISTENCE",
        },
    },
    "CHECK_PATIENT_EXISTENCE": {
        "next_state": {
            "true": "EXISTING_PATIENT_MENU",
            "false": "MAIN_MENU",
        },
        "previous_state": "LANGUAGE_SELECTION",
    },
    "EXISTING_PATIENT_MENU": {
        "next_state": {
            "1": "VIEW_DETAILS",
            "2": "LIST_SEGMENTS",
            "3": "OPT_OUT",
            "4": "LANGUAGE_SELECTION",
        },
        "previous_state": "CHECK_PATIENT_EXISTENCE",
    },
    "VIEW_DETAILS": {
        "next_state": {
            "0": "EXISTING_PATIENT_MENU",
        },
        "previous_state": "EXISTING_PATIENT_MENU",
    },
    "LIST_SEGMENTS": {
        "next_state": {
            "0": "EXISTING_PATIENT_MENU",
            "default": "CONFIRM_ENROLLMENT",
        },
        "previous_state": "EXISTING_PATIENT_MENU",
    },
    "CONFIRM_ENROLLMENT": {
        "next_state": {
            "2": "EXISTING_PATIENT_MENU",
            "default": "ENROLL_TO_SEGMENT",
        },
        "previous_state": "LIST_SEGMENTS",
    },
    "ENROLL_TO_SEGMENT": {
        "next_state": {
            "1": "ENROLLMENT_SUCCESSFUL",
            "2": "ENROLLMENT_FAILED",
            "3": "EXISTING_PATIENT_MENU",
        },
        "previous_state": "CONFIRM_ENROLLMENT",
    },
    "OPT_OUT": {
        "next_state": {
            "1": "CONFIRM_OPT_OUT",
            "2": "EXISTING_PATIENT_MENU",
        },
        "previous_state": "EXISTING_PATIENT_MENU",
    },
    "MAIN_MENU": {
        "next_state": {
            "1": "SELECT_REGION",
            "2": "LANGUAGE_SELECTION",
        },
        "previous_state": "LANGUAGE_SELECTION",
    },
    "SELECT_REGION": {
        "next_state": {
            "0": "MAIN_MENU",
            "default": "ENTER_NAME",
        },
        "previous_state": "LANGUAGE_SELECTION",
    },
    "ENTER_NAME": {
        "next_state": {
            "0": "MAIN_MENU",
            "default": "ENTER_DOB",
        },
        "previous_state": "SELECT_REGION",
    },
    "ENTER_DOB": {
        "next_state": {
            "0": "MAIN_MENU",
            "default": "ENTER_GENDER",
        },
        "previous_state": "ENTER_NAME",
    },
    "ENTER_GENDER": {
        "next_state": {
            "0": "MAIN_MENU",
            "default": "CONFIRM_REGISTRATION",
        },
        "previous_state": "ENTER_DOB",
    },
    "CONFIRM_REGISTRATION": {
        "next_state": {
            "0": "MAIN_MENU",
            "1": "CONSENT_SMS",
            "2": "REGISTRATION_CANCELLED",
        },
        "previous_state": "ENTER_GENDER",
    },
    "CONSENT_SMS": {
        "next_state": {
            "0": "MAIN_MENU",
            "default": "REGISTRATION_SUCCESSFUL",
        },
        "previous_state": "CONFIRM_REGISTRATION",
    },
    "REGISTRATION_SUCCESSFUL": {
        "next_state": {},
        "previous_state": "CONSENT_SMS",
    },
    "REGISTRATION_CANCELLED": {
        "next_state": {},
        "previous_state": "CONFIRM_REGISTRATION",
    },
}

MESSAGES = {
    "en": {
        "LANGUAGE_SELECTION": (
            "CON Welcome to Uzazi Salama, "
            "please select your preferred language to proceed:"
            "\n1. English\n2. Kiswahili"
        ),
        "EXISTING_PATIENT_MENU": (
            "CON Please select a service:\n"
            "1. View My Details\n"
            "2. Enroll to Health Education\n"
            "3. Opt out of Uzazi Salama\n"
            "4. Change Language\n"
        ),
        "VIEW_DETAILS": (
            "CON Hello, {first_name}, here are your registered details:\n"
            "Name: {first_name} {last_name}\n"
            "Phone Number: {phone_number}\n"
            "Date of Birth: {date_of_birth}\n"
            "Gender: {gender}\n\n"
            "0. Back to Main Menu"
        ),
        "LIST_SEGMENTS": (
            "CON Select a Category you would like to enroll to:\n{segments}"
            "\n\n0. Back to Main Menu"
        ),
        "CONFIRM_ENROLLMENT": (
            "CON Confirm Enrollment to {segment}:\n1. Accept\n2. Reject"
        ),
        "ENROLLMENT_SUCCESSFUL": (
            "END You have been successfully enrolled to the Program. "
            "You will receive an SMS shortly confirming your enrollment.\n"
        ),
        "ENROLLMENT_FAILED": "END Enrollment failed. Please try again.",
        "OPT_OUT": (
            "CON Kindly confirm that you want to opt out of the program.\n"
            "1. Confirm\n"
            "2. Reject"
        ),
        "OPT_OUT_SUCCESSFUL": "END You have successfully opted out.",
        "OPT_OUT_FAILED": "END Opt-out failed. Please try again.",
        "MAIN_MENU": (
            "CON Please select a service:\n1. Register Myself\n2. Change Language"
        ),
        "SELECT_EN_REGION": (
            "CON Select your region:\n{regions}\n0. Back to Main Menu"
        ),
        "SELECT_REGION": ("CON Select your region:\n{regions}\n0. Back to Main Menu"),
        "ENTER_NAME": (
            "CON To register, please enter your first and last name "
            "(Eg Jane Kaberu):\n0. Back to Main Menu"
        ),
        "ENTER_DOB": "CON Enter Date of Birth (DD/MM/YYYY):\n0. Back to Main Menu",
        "ENTER_GENDER": (
            "CON Select Gender:\n1. Male\n2. Female\n3. Other\n0. Back to Main Menu"
        ),
        "CONFIRM_REGISTRATION": (
            "CON Confirm registration to Uzazi Salama program:\n"
            "Name: {name}\n"
            "Date of Birth: {dob}\n"
            "Gender: {gender}\n\n"
            "1. Confirm\n2. Cancel\n0. Back to Main Menu"
        ),
        "CONSENT_SMS": (
            "CON Would you like to receive SMS from Uzazi Salama? "
            "Select 1 to accept or 2 to reject:\n"
            "1. Accept\n"
            "2. Reject\n\n0. Back to Main Menu"
        ),
        "REGISTRATION_SUCCESSFUL": (
            "END You have successfully been registered to Uzazi Salama. "
            "You will receive an SMS shortly confirming your registration."
        ),
        "REGISTRATION_CANCELLED": "END Registration cancelled.",
        "REGISTRATION_FAILED": "END Registration failed. Please try again.",
    },
    "sw": {
        "LANGUAGE_SELECTION": (
            "CON Karibu Uzazi Salama, "
            "tafadhali chagua lugha unayopendelea kuendelea:"
            "\n1. Kiingereza\n2. Kiswahili"
        ),
        "EXISTING_PATIENT_MENU": (
            "CON Chagua Huduma:\n"
            "1. Tazama maelezo yangu\n"
            "2. Jisajili kwa elimu\n"
            "3. Chagua kutoka kwa programu ya Uzazi Salama\n"
            "4. Badilisha Lugha\n"
        ),
        "VIEW_DETAILS": (
            "CON Hujambo, {first_name}, haya hapa ni maelezo "
            "yako yaliyosajiliwa:\n"
            "Jina: {first_name} {last_name}\n"
            "Nambari ya simu: {phone_number}\n"
            "Mwaka wa kuzaliwa: {date_of_birth}\n"
            "Jinsia: {gender}\n"
            "0. Rudi Kwenye Menyu Kuu"
        ),
        "LIST_SEGMENTS": "CON Chagua Kategoria unayotaka kujisajili:\n{segments}"
        "\n\n0. Rudi kwenye Menyu Kuu",
        "CONFIRM_ENROLLMENT": (
            "CON Thibitisha usajili wa {segment}:\n1. Kubali\n2. Kataa\n"
        ),
        "ENROLLMENT_SUCCESSFUL": (
            "END Umefanikiwa kujisajili kwa mafunzo. "
            "Utapokea ujumbe wa SMS hivi karibuni kuthibitisha usajili wako.\n"
        ),
        "ENROLLMENT_FAILED": "END Usajili umekuwa na hitilafu. Tafadhali jaribu tena.",
        "OPT_OUT": (
            "CON Tafadhali thibitisha kuwa unataka kujiondoa kwenye programu.\n"
            "1. Kubali\n"
            "2. Kataa"
        ),
        "OPT_OUT_SUCCESSFUL": (
            "END Umefanikiwa kujiondoa kwenye programu ya uzazi salama."
        ),
        "OPT_OUT_FAILED": "END Kujiondoa kumeleta hitilafu. Tafadhali jaribu tena.",
        "MAIN_MENU": "CON Tafadhali chagua huduma:\n1. Jisajili\n2. Badilisha Lugha",
        "SELECT_EN_REGION": (
            "CON Chagua eneo lako:\n{regions}\n0. Rudi kwenye Menyu Kuu"
        ),
        "SELECT_REGION": ("CON Chagua eneo lako:\n{regions}\n0. Rudi kwenye Menyu Kuu"),
        "ENTER_NAME": (
            "CON Kujisajili, tafadhali ingiza jina lako la kwanza na la mwisho "
            "(Mfano Jane Kaberu):\n0. Rudi kwenye Menyu Kuu"
        ),
        "ENTER_DOB": (
            "CON Weka Tarehe ya Kuzaliwa (DD/MM/YYYY):\n0. Rudi kwenye Menyu Kuu"
        ),
        "ENTER_GENDER": (
            "CON Chagua Jinsia:"
            "\n1. Mwanaume\n2. Mwanamke\n3. Nyingine\n0. Rudi kwenye Menyu Kuu"
        ),
        "CONSENT_SMS": (
            "CON Ungependa Kupokea SMS kutoka Uzazi Salama? "
            "Chagua 1 kukubali au 2 kukataa:\n"
            "1. Ndio\n"
            "2. Hapana\n0.Rudi kwenye Menyu Kuu"
        ),
        "CONFIRM_REGISTRATION": (
            "CON Hakikisha usajili kwenye programu ya uzazi salama:\n"
            "Jina: {name}\n"
            "Tarehe ya Kuzaliwa: {dob}\n"
            "Jinsia: {gender}\n\n"
            "1. Thibitisha\n2. Ghairi\n0. Rudi kwenye Menyu Kuu"
        ),
        "REGISTRATION_SUCCESSFUL": (
            "END Asante kwa kujisajili na Programu ya Uzazi Salama."
            "Utapokea ujumbe mfupi wa maandishi wa uthibitisho hivi karibuni."
        ),
        "REGISTRATION_CANCELLED": "END Usajili umeghairiwa.",
        "REGISTRATION_FAILED": (
            "END Usajili umekuwa na hitilafu. Tafadhali jaribu tena."
        ),
    },
}

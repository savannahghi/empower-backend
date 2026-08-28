"""Settings app."""
from sil_advantage.billing.settings import (
    BRANCH_BILLING_SETTINGS,
    ORG_BILLING_SETTINGS,
)
from sil_advantage.notifications.sms.settings import (
    BRANCH_SMS_SETTINGS,
    ORG_SMS_SETTINGS,
)
from sil_advantage.patients.settings import (
    BRANCH_PATIENTS_SETTINGS,
    ORG_PATIENTS_SETTINGS,
)
from sil_advantage.scheduling.settings import (
    BRANCH_SCHEDULING_SETTINGS,
    ORG_SCHEDULING_SETTINGS,
)
from sil_advantage.visits.settings import (
    BRANCH_VISITS_SETTINGS,
    ORG_VISITS_SETTINGS,
)

ORGANISATION_SETTINGS = {}
ORGANISATION_SETTINGS.update(
    {manager.name: manager for manager in ORG_PATIENTS_SETTINGS}
)
ORGANISATION_SETTINGS.update({manager.name: manager for manager in ORG_SMS_SETTINGS})
ORGANISATION_SETTINGS.update(
    {manager.name: manager for manager in ORG_SCHEDULING_SETTINGS}
)
ORGANISATION_SETTINGS.update(
    {manager.name: manager for manager in ORG_BILLING_SETTINGS}
)
ORGANISATION_SETTINGS.update({manager.name: manager for manager in ORG_VISITS_SETTINGS})

# Add branch settings alongside organisation settings
BRANCH_SETTINGS = {}
BRANCH_SETTINGS.update({manager.name: manager for manager in BRANCH_BILLING_SETTINGS})
BRANCH_SETTINGS.update({manager.name: manager for manager in BRANCH_SMS_SETTINGS})
BRANCH_SETTINGS.update({manager.name: manager for manager in BRANCH_PATIENTS_SETTINGS})
BRANCH_SETTINGS.update(
    {manager.name: manager for manager in BRANCH_SCHEDULING_SETTINGS}
)
BRANCH_SETTINGS.update({manager.name: manager for manager in BRANCH_VISITS_SETTINGS})

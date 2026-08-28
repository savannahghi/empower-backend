"""Common views module."""
from .bp_registry_views import BPRegistryView
from .common_views import (
    ConsentTransitionView,
    ConsentViewSet,
    OperatingRegionViewSet,
    OrganisationViewSet,
    PersonAttachmentViewSet,
    PersonContactViewSet,
    PersonIDViewSet,
    PersonViewSet,
    PractitionerViewSet,
    RelatedPersonViewSet,
    UserProfileViewSet,
)
from .erp import ERPView
from .home import HomePageView
from .onboarding import OnboardingViewSet, OrganisationOnboardingViewSet

__all__ = [
    "BPRegistryView",
    "ERPView",
    "HomePageView",
    "OnboardingViewSet",
    "OrganisationOnboardingViewSet",
    "OrganisationViewSet",
    "PersonAttachmentViewSet",
    "PersonContactViewSet",
    "PersonIDViewSet",
    "PersonViewSet",
    "RelatedPersonViewSet",
    "UserProfileViewSet",
    "PractitionerViewSet",
    "ConsentViewSet",
    "ConsentTransitionView",
    "OperatingRegionViewSet",
]

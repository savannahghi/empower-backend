"""Assemble all URLs from the common app."""
from django.urls import path
from rest_framework.routers import SimpleRouter

from sil_advantage.common.views import (
    BPRegistryView,
    ConsentTransitionView,
    ConsentViewSet,
    OnboardingViewSet,
    RealmRoleView,
    OperatingRegionViewSet,
    OrganisationOnboardingViewSet,
    UserViewSet,
    OrganisationViewSet,
    PersonAttachmentViewSet,
    PersonContactViewSet,
    PersonIDViewSet,
    PersonViewSet,
    PractitionerViewSet,
    RelatedPersonViewSet,
    UserProfileViewSet,
)

router = SimpleRouter()
router.register("organisations", OrganisationViewSet)
router.register("persons", PersonViewSet)
router.register("related_persons", RelatedPersonViewSet)
router.register("contacts", PersonContactViewSet, "contacts")
router.register("user_identification", PersonIDViewSet)
router.register("person_attachments", PersonAttachmentViewSet)
router.register("user_profiles", UserProfileViewSet)
router.register("practitioners", PractitionerViewSet)
router.register("onboarding", OnboardingViewSet, basename="onboarding")
router.register("organisation_onboarding", OrganisationOnboardingViewSet)
router.register("consent", ConsentViewSet)
router.register("users", UserViewSet, basename="users")
router.register("operating_regions", OperatingRegionViewSet)

urlpatterns = [
    path("realm_roles/", RealmRoleView.as_view(), name="realm-roles"),
]
urlpatterns += router.urls
urlpatterns += (
    path(
        "bp_registry/",
        BPRegistryView.as_view(),
        name="bpregistry-list",
    ),
)

urlpatterns += (
    path(
        "consent/<uuid:id>/transition/<slug:status>/",
        ConsentTransitionView.as_view(),
        name="consent-transition",
    ),
)

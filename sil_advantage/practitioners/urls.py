"""Practitioner app urls."""
from rest_framework.routers import SimpleRouter

from sil_advantage.practitioners.views import PractitionerViewSet

router = SimpleRouter()
router.register("practitioners", PractitionerViewSet)
urlpatterns = router.urls

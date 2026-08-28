"""Prescription URLs."""
from rest_framework.routers import SimpleRouter

from sil_advantage.prescriptions import views

router = SimpleRouter()
router.register("prescriptions", views.PrescriptionViewSet, "prescriptions")

urlpatterns = router.urls

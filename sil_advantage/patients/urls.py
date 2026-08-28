"""Patients app URL endpoints."""
from rest_framework.routers import SimpleRouter

from sil_advantage.patients.views import (
    PatientCoverViewSet,
    PatientDocumentViewSet,
    PatientListUploadViewSet,
    PatientViewSet,
)

router = SimpleRouter()
router.register("patients", PatientViewSet)
router.register("patient_documents", PatientDocumentViewSet)
router.register("patientcovers", PatientCoverViewSet)
router.register("patient_list_uploads", PatientListUploadViewSet)


urlpatterns = router.urls

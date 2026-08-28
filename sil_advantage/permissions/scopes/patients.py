"""Patients scopes."""
from sil_auth_backends.utilities.utilities import SCOPE_NODE

# Patients

PATIENT_READ = SCOPE_NODE(
    "advantage.patient.read",
    "View patients",
)
PATIENT_WRITE = SCOPE_NODE(
    "advantage.patient.write",
    "Edit patients",
)

# Patient Documents

PATIENT_DOCUMENT_READ = SCOPE_NODE(
    "advantage.patient_document.read",
    "View patient documents",
)
PATIENT_DOCUMENT_WRITE = SCOPE_NODE(
    "advantage.patient_document.write",
    "Edit patient documents",
)

# Patient List Uploads

PATIENT_LIST_UPLOAD_READ = SCOPE_NODE(
    "advantage.patient_list_upload.read",
    "View patient list uploads",
)
PATIENT_LIST_UPLOAD_WRITE = SCOPE_NODE(
    "advantage.patient_list_upload.write",
    "Edit patient list uploads",
)

"""Patients permissions."""
from sil_auth_backends.utilities.utilities import PERM_NODE

# Patients

PATIENT_VIEW = PERM_NODE(
    "advantage.patient_list",
    "View patients",
)

PATIENT_CREATE = PERM_NODE(
    "advantage.patient_create",
    "Create patients",
)

PATIENT_EDIT = PERM_NODE(
    "advantage.patient_edit",
    "Edit patients",
)

PATIENT_DELETE = PERM_NODE(
    "advantage.patient_delete",
    "Remove patients",
)

# Patient Documents

PATIENT_DOCUMENT_VIEW = PERM_NODE(
    "advantage.patient_document_list",
    "View patient documents",
)

PATIENT_DOCUMENT_CREATE = PERM_NODE(
    "advantage.patient_document_create",
    "Upload patient documents",
)

PATIENT_DOCUMENT_EDIT = PERM_NODE(
    "advantage.patient_document_edit",
    "Edit patient documents",
)

PATIENT_DOCUMENT_DELETE = PERM_NODE(
    "advantage.patient_document_delete",
    "Delete patient documents",
)

PATIENT_DOCUMENT_REVIEW = PERM_NODE(
    "advantage.patient_document_review",
    "Review patient documents",
    children=(
        PATIENT_DOCUMENT_VIEW,
        PATIENT_DOCUMENT_CREATE,
        PATIENT_DOCUMENT_EDIT,
    ),
)

# Patient List Uploads

PATIENT_LIST_UPLOAD_VIEW = PERM_NODE(
    "advantage.patient_list_upload_list",
    "View patient list uploads",
)

PATIENT_LIST_UPLOAD_CREATE = PERM_NODE(
    "advantage.patient_list_upload_create",
    "Create patient list uploads",
)

PATIENT_LIST_UPLOAD_EDIT = PERM_NODE(
    "advantage.patient_list_upload_edit",
    "Edit patient list uploads",
)

PATIENT_LIST_UPLOAD_DELETE = PERM_NODE(
    "advantage.patient_list_upload_delete",
    "Delete patient list uploads",
)

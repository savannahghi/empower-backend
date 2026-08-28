"""Files tasks."""
import io
import logging

from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import transaction
from django.utils import timezone
from googleapiclient.discovery import Resource

from sil_advantage.common.models import Organisation
from sil_advantage.integrations.files.base import AbstractFile
from sil_advantage.patients.models import Patient, PatientDocument
from sil_advantage.sil_auth.models import SILUser

LOGGER = logging.getLogger(__file__)


def validate_patient_record(file: AbstractFile, org: Organisation) -> bool:
    """Validate a patient file record."""
    file_no = file.name.split(".")[0]
    if not file_no.isnumeric():
        LOGGER.error(f"Invalid file number {file_no}.")
        return False

    if file.mime_type != "application/pdf":
        LOGGER.warning(
            (
                f"Unknown file type {file.mime_type} for "
                f"patient record with name {file_no}."
            )
        )
        return False

    if file.size > settings.MAX_UPLOAD_SIZE:
        LOGGER.warning(f"Patient file {file_no} is too big.")
        return False

    patient = Patient.objects.filter(file_number=file_no, organisation=org)
    if not patient.exists():
        LOGGER.error(f"Patient matching file # {file_no} doesn't exist.")
        return False
    return True


def download_patient_record(file: AbstractFile) -> bool:
    """Download a patient file record.

    The file must be in a folder tree like so:
        SIL Main Folder
            --- Provider - Slade Code
                    --- Pending
                    --- Processed
                    --- Failed
                    --- Existing
    """
    file_no = file.name.split(".")[0]
    if (
        file.parent is None
        or file.parent.name != "Pending"
        or file.parent.parent is None
    ):
        LOGGER.error(f"File {file_no} in wrong folder.")
        return False

    grandparent_folder = file.parent.parent
    slade_code = grandparent_folder.name.split("-")[-1].strip()
    if (
        not slade_code.isnumeric()
        or not Organisation.objects.filter(slade_code=slade_code).exists()
    ):
        LOGGER.error(f"Unknown organisation with slade code {slade_code}.")
        return False

    # This should be in the Google Drive adapter
    drive: Resource = file.adapter
    assert grandparent_folder.metadata is not None
    post_processing_folders = (
        drive.files()
        .list(
            q=(
                "mimeType='application/vnd.google-apps.folder'"
                f"and '{grandparent_folder.metadata['id']}' in parents"
            ),
            fields="files(id, name)",
        )
        .execute()["files"]
    )
    names = set(folder["name"] for folder in post_processing_folders)
    if not set(["Processed", "Failed", "Existing"]).issubset(names):
        LOGGER.error("Post processing folders don't exist.")
        return False

    org_obj = Organisation.objects.get(slade_code=slade_code)
    failed = not validate_patient_record(file, org_obj)

    existing = False
    doc = PatientDocument.objects.filter(file_hash=file.hash)
    if not failed and doc.exists():
        LOGGER.warning(f"Document # {file_no} already exists.")
        existing = True

    document_no = f"File {file.name}"
    if not failed and not existing:
        file_content = InMemoryUploadedFile(
            io.BytesIO(file.read()),
            None,
            document_no,
            "application/pdf",
            file.size,
            None,
            {},
        )

        patient = Patient.objects.get(
            file_number=file_no,
            organisation=org_obj,
        )
        with transaction.atomic():
            # Set network admin as the created_by and updated_by fields
            admin_email = settings.SYSTEM_ADMIN_EMAIL
            system_admin = SILUser.objects.get(email=admin_email).id

            PatientDocument.objects.create(
                patient=patient,
                document_number=document_no,
                document_type="CLINICAL_NOTES",
                title=document_no,
                content_type="application/pdf",
                size=file.size,
                data=file_content,
                visit_date=timezone.now(),
                file_hash=file.hash,
                organisation=org_obj,
                created_by=system_admin,
                updated_by=system_admin,
            )
            folder = [
                folder
                for folder in post_processing_folders
                if folder["name"] == "Processed"
            ][0]
            file.move(folder["id"])
        LOGGER.info(f"Downloaded patient record {document_no}.")
        return True
    elif existing:
        folder = [
            folder for folder in post_processing_folders if folder["name"] == "Existing"
        ][0]
        file.move(folder["id"])
        return True
    else:
        folder = [
            folder for folder in post_processing_folders if folder["name"] == "Failed"
        ][0]
        file.move(folder["id"])
        return False

"""Test Google Drive Integration."""
import io
from dataclasses import dataclass
from random import randint
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import uuid4

from django.core.cache import cache
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.urls import reverse
from google.oauth2.service_account import Credentials
from model_bakery import baker

from sil_advantage.integrations.files.google_drive import (
    GoogleDriveFile,
    open_google_drive_channels,
)
from sil_advantage.integrations.models import IntegrationConfig
from sil_advantage.patients.models import Patient, PatientDocument
from sil_advantage.sil_auth.models import SILUser
from tests.common.test_common_views import LoggedInMixin

MOCK_ROOT = "sil_advantage.integrations.files.google_drive."
MOCK_UTILS = "sil_advantage.integrations.files.utils."


@dataclass
class FakeFolder:
    """A fake folder."""

    name: str
    size: int
    mime_type: str
    created: Any
    modified: Any
    metadata: dict
    adapter: Any
    org: str

    @property
    def parent(self):
        """Fake parent."""
        return FakeFolder(
            f"Oregon - {self.org}",
            0,
            "application/vnd.google-apps.folder",
            None,
            None,
            {"id": "2342345"},
            self.adapter,
            50,
        )


class GoogleDriveIntegrationTest(LoggedInMixin):
    """Test Google Drive Integration."""

    url = reverse("google-drive")

    def setUp(self):
        """Set up the test environment."""
        super().setUp()
        # setup system-admin
        baker.make(SILUser, email="network.admin@slade360.co.ke")
        self.patient = baker.make(Patient, file_number=1)
        self.config = IntegrationConfig.objects.create(
            system="GOOGLE_DRIVE",
            role="PATIENT_RECORDS_UPLOAD",
            config={
                "type": "service_account",
                "project_id": "some-project",
                "private_key_id": "asdfasdf",
                "private_key": "asdfasdfasdf",
                "client_email": "drive@some-project.iam.gserviceaccount.com",
                "client_id": "456345634563456",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/",
                "client_x509_cert_url": "https://www.googleapis.com/robot/",
                "universe_domain": "googleapis.com",
            },
            metadata={"pageToken": "34"},
            organisations=[5113],
            created_by=uuid4(),
            updated_by=uuid4(),
        )

        blank_config = baker.make(IntegrationConfig, config=None)
        blank_config.refresh_from_db()
        assert blank_config.config is None

    @patch.object(GoogleDriveFile, "new")
    def test_get_file_parent(self, mock_new):
        """Test getting the file's parent."""
        file = GoogleDriveFile(
            "fasdf", 5, "application/json", None, None, {"parent": None}, None
        )
        assert file.parent is None

        del file.parent
        file.metadata["parent"] = "1222"
        assert file.parent is not None

    @patch.object(GoogleDriveFile, "parent", new_callable=PropertyMock)
    @patch(MOCK_UTILS + "LOGGER")
    @patch(MOCK_ROOT + "MediaIoBaseDownload")
    @patch(MOCK_ROOT + "get_google_drive_client")
    @patch.object(Credentials, "from_service_account_info")
    def test_successful_patient_file_upload(
        self,
        mock_credz,
        mock_drive,
        mock_download,
        mock_logger,
        mock_parent,
    ):
        """Test successful patient file upload."""
        mock_credz.return_value = MagicMock()
        mock_changes = mock_drive.return_value.changes.return_value
        mock_changes.list.return_value.execute.return_value = {
            "newStartPageToken": 89,
            "changes": [
                {
                    "file": {
                        "id": "234324",
                        "mimeType": "application/pdf",
                    }
                }
            ],
        }
        mock_files = mock_drive.return_value.files.return_value
        mock_files.get.return_value.execute.return_value = {
            "mimeType": "application/pdf",
            "size": "200",
            "name": "1",
            "id": "234324",
            "createdTime": "123",
            "modifiedTime": "23",
            "md5Checksum": "42",
            "parents": ["ppp"],
        }
        mock_files.list.return_value.execute.return_value = {
            "files": [
                {"name": "Processed", "id": "324234"},
                {"name": "Existing", "id": "324235"},
                {"name": "Failed", "id": "324236"},
            ]
        }
        mock_parent.return_value = FakeFolder(
            "Pending",
            0,
            "application/vnd.google-apps.folder",
            None,
            None,
            None,
            mock_drive,
            50,
        )
        download = MagicMock()
        download.next_chunk.return_value = None, True
        mock_download.return_value = download

        document = PatientDocument.objects.filter(
            title="File 1",
            patient=self.patient,
        )
        assert not document.exists()
        lock_key = "google_drive_file_lock_234324"
        assert cache.get(lock_key, None) is None

        response = self.client.post(
            self.url,
            headers={
                "X-Goog-Channel-ID": f"{self.config.pk}+{randint(1_000, 9_999)}",
                "X-Goog-Resource-State": "change",
                "X-Goog-Resource-ID": "fLt2rIVtXlXxBKz2JJaFD",
            },
        )

        assert response.status_code == 200
        mock_logger.info.assert_called_once_with("Downloaded patient record File 1.")
        assert document.exists()
        assert cache.get(lock_key, None) is True

        # test idempotency
        mock_logger.reset_mock()
        self.client.post(
            self.url,
            headers={
                "X-Goog-Channel-ID": f"{self.config.pk}+{randint(1_000, 9_999)}",
                "X-Goog-Resource-State": "change",
                "X-Goog-Resource-ID": "fLt2rIVtXlXxBKz2JJaFD",
            },
        )
        mock_logger.info.assert_not_called()

    @patch(MOCK_ROOT + "process_google_drive_notification")
    def test_trigger_callback_with_invalid_resource_state(self, mock_task):
        """Test triggering the callback with an invalid resource state."""
        response = self.client.post(
            self.url,
            headers={
                "X-Goog-Channel-ID": f"{self.config.pk}+{randint(1_000, 9_999)}",
                "X-Goog-Resource-State": "trash",
                "X-Goog-Resource-ID": "fLt2rIVtXlXxBKz2JJaFD",
            },
        )
        assert response.status_code == 200
        mock_task.apply_async.assert_not_called()

    @patch.object(GoogleDriveFile, "parent", new_callable=PropertyMock)
    @patch(MOCK_UTILS + "LOGGER")
    @patch(MOCK_ROOT + "build")
    @patch.object(Credentials, "from_service_account_info")
    def test_validate_record_mime_type(
        self, mock_credz, mock_drive, mock_logger, mock_parent
    ):
        """Test validate file mime type."""
        mock_credz.return_value = MagicMock()
        mock_changes = mock_drive.return_value.changes.return_value
        mock_changes.list.return_value.execute.return_value = {
            "newStartPageToken": 89,
            "changes": [
                {
                    "file": {
                        "id": "234324",
                        "mimeType": "audio/mpeg",
                    }
                }
            ],
        }
        mock_files = mock_drive.return_value.files.return_value
        mock_files.get.return_value.execute.return_value = {
            "mimeType": "audio/mpeg",
            "size": "200",
            "name": "1",
            "id": "fLt2rIVtXlXxBKz2JJaFD",
            "createdTime": "123",
            "modifiedTime": "23",
            "md5Checksum": "42",
            "parents": ["ppp"],
        }
        mock_files.list.return_value.execute.return_value = {
            "files": [
                {"name": "Processed", "id": "324234"},
                {"name": "Existing", "id": "324235"},
                {"name": "Failed", "id": "324236"},
            ]
        }
        mock_parent.return_value = FakeFolder(
            "Pending",
            0,
            "application/vnd.google-apps.folder",
            None,
            None,
            None,
            mock_drive,
            50,
        )

        response = self.client.post(
            self.url,
            headers={
                "X-Goog-Channel-ID": f"{self.config.pk}+{randint(1_000, 9_999)}",
                "X-Goog-Resource-State": "change",
                "X-Goog-Resource-ID": "fLt2rIVtXlXxBKz2JJaFD",
            },
        )

        assert response.status_code == 200
        mock_logger.warning.assert_called_once_with(
            "Unknown file type audio/mpeg " "for patient record with name 1."
        )
        document = PatientDocument.objects.filter(
            title="FILE 1",
            patient=self.patient,
        )
        assert not document.exists()

    @patch.object(GoogleDriveFile, "parent", new_callable=PropertyMock)
    @patch(MOCK_UTILS + "LOGGER")
    @patch(MOCK_ROOT + "build")
    @patch.object(Credentials, "from_service_account_info")
    def test_validate_upload_size(
        self, mock_credz, mock_drive, mock_logger, mock_parent
    ):
        """Test validating file upload size."""
        mock_credz.return_value = MagicMock()
        mock_changes = mock_drive.return_value.changes.return_value
        mock_changes.list.return_value.execute.return_value = {
            "newStartPageToken": 89,
            "changes": [
                {
                    "file": {
                        "id": "234324",
                        "mimeType": "application/pdf",
                    }
                }
            ],
        }
        mock_files = mock_drive.return_value.files.return_value
        mock_files.get.return_value.execute.return_value = {
            "mimeType": "application/pdf",
            "size": "200457356476456456",
            "name": "1",
            "id": "fLt2rIVtXlXxBKz2JJaFD",
            "createdTime": "123",
            "modifiedTime": "23",
            "md5Checksum": "42",
        }
        mock_files.list.return_value.execute.return_value = {
            "files": [
                {"name": "Processed", "id": "324234"},
                {"name": "Existing", "id": "324235"},
                {"name": "Failed", "id": "324236"},
            ]
        }
        mock_parent.return_value = FakeFolder(
            "Pending",
            0,
            "application/vnd.google-apps.folder",
            None,
            None,
            None,
            mock_drive,
            50,
        )

        response = self.client.post(
            self.url,
            headers={
                "X-Goog-Channel-ID": f"{self.config.pk}+{randint(1_000, 9_999)}",
                "X-Goog-Resource-State": "change",
                "X-Goog-Resource-ID": "fLt2rIVtXlXxBKz2JJaFD",
            },
        )

        assert response.status_code == 200
        mock_logger.warning.assert_called_once_with("Patient file 1 is too big.")
        document = PatientDocument.objects.filter(
            title="FILE 1",
            patient=self.patient,
        )
        assert not document.exists()

    @patch.object(GoogleDriveFile, "parent", new_callable=PropertyMock)
    @patch(MOCK_UTILS + "LOGGER")
    @patch(MOCK_ROOT + "build")
    @patch.object(Credentials, "from_service_account_info")
    def test_check_if_patient_exists(
        self, mock_credz, mock_drive, mock_logger, mock_parent
    ):
        """Test validating file upload size."""
        mock_credz.return_value = MagicMock()
        mock_changes = mock_drive.return_value.changes.return_value
        mock_changes.list.return_value.execute.return_value = {
            "newStartPageToken": 89,
            "changes": [
                {
                    "file": {
                        "id": "234324",
                        "mimeType": "application/pdf",
                    }
                }
            ],
        }
        mock_files = mock_drive.return_value.files.return_value
        mock_files.get.return_value.execute.return_value = {
            "mimeType": "application/pdf",
            "size": "200",
            "name": "190909",
            "id": "fLt2rIVtXlXxBKz2JJaFD",
            "createdTime": "123",
            "modifiedTime": "23",
            "md5Checksum": "42",
            "parents": ["ppp"],
        }
        mock_files.list.return_value.execute.return_value = {
            "files": [
                {"name": "Processed", "id": "324234"},
                {"name": "Existing", "id": "324235"},
                {"name": "Failed", "id": "324236"},
            ]
        }
        mock_parent.return_value = FakeFolder(
            "Pending",
            0,
            "application/vnd.google-apps.folder",
            None,
            None,
            None,
            mock_drive,
            50,
        )

        lock_key = "google_drive_file_lock_234324"
        assert cache.get(lock_key, None) is None

        response = self.client.post(
            self.url,
            headers={
                "X-Goog-Channel-ID": f"{self.config.pk}+{randint(1_000, 9_999)}",
                "X-Goog-Resource-State": "change",
                "X-Goog-Resource-ID": "fLt2rIVtXlXxBKz2JJaFD",
            },
        )

        assert response.status_code == 200
        mock_logger.error.assert_called_once_with(
            "Patient matching file # 190909 doesn't exist."
        )
        document = PatientDocument.objects.filter(patient=self.patient)
        assert not document.exists()
        assert cache.get(lock_key, None) is None

    @patch.object(GoogleDriveFile, "parent", new_callable=PropertyMock)
    @patch(MOCK_UTILS + "LOGGER")
    @patch(MOCK_ROOT + "build")
    @patch.object(Credentials, "from_service_account_info")
    def test_validate_file_number_is_numeric(
        self, mock_credz, mock_drive, mock_logger, mock_parent
    ):
        """Test validating that the file number is numeric."""
        mock_credz.return_value = MagicMock()
        mock_changes = mock_drive.return_value.changes.return_value
        mock_changes.list.return_value.execute.return_value = {
            "newStartPageToken": 89,
            "changes": [
                {
                    "file": {
                        "id": "234324",
                        "mimeType": "application/pdf",
                    }
                }
            ],
        }
        mock_files = mock_drive.return_value.files.return_value
        mock_files.get.return_value.execute.return_value = {
            "mimeType": "application/pdf",
            "size": "200",
            "name": "ert234",
            "id": "fLt2rIVtXlXxBKz2JJaFD",
            "createdTime": "123",
            "modifiedTime": "23",
            "md5Checksum": "42",
            "parents": ["ppp"],
        }
        mock_files.list.return_value.execute.return_value = {
            "files": [
                {"name": "Processed", "id": "324234"},
                {"name": "Existing", "id": "324235"},
                {"name": "Failed", "id": "324236"},
            ]
        }
        mock_parent.return_value = FakeFolder(
            "Pending",
            0,
            "application/vnd.google-apps.folder",
            None,
            None,
            None,
            mock_drive,
            50,
        )

        response = self.client.post(
            self.url,
            headers={
                "X-Goog-Channel-ID": f"{self.config.pk}+{randint(1_000, 9_999)}",
                "X-Goog-Resource-State": "change",
                "X-Goog-Resource-ID": "fLt2rIVtXlXxBKz2JJaFD",
            },
        )

        assert response.status_code == 200
        mock_logger.error.assert_called_once_with("Invalid file number ert234.")
        document = PatientDocument.objects.filter(patient=self.patient)
        assert not document.exists()

    @patch.object(GoogleDriveFile, "parent", new_callable=PropertyMock)
    @patch(MOCK_UTILS + "LOGGER")
    @patch(MOCK_ROOT + "build")
    @patch.object(Credentials, "from_service_account_info")
    def test_validate_folder_structure(
        self, mock_credz, mock_drive, mock_logger, mock_parent
    ):
        """Test validating the folder structure."""
        mock_credz.return_value = MagicMock()
        mock_changes = mock_drive.return_value.changes.return_value
        mock_changes.list.return_value.execute.return_value = {
            "newStartPageToken": 89,
            "changes": [
                {
                    "file": {
                        "id": "234324",
                        "mimeType": "application/pdf",
                    }
                }
            ],
        }
        mock_files = mock_drive.return_value.files.return_value
        mock_files.get.return_value.execute.return_value = {
            "mimeType": "application/pdf",
            "size": "200",
            "name": "1",
            "id": "fLt2rIVtXlXxBKz2JJaFD",
            "createdTime": "123",
            "modifiedTime": "23",
            "md5Checksum": "42",
            "parents": ["ppp"],
        }
        mock_files.list.return_value.execute.return_value = {
            "files": [
                {"name": "Processed", "id": "324234"},
                {"name": "Existing", "id": "324235"},
                {"name": "Failed", "id": "324236"},
            ]
        }
        mock_parent.return_value = FakeFolder(
            "Pendingz",
            0,
            "application/vnd.google-apps.folder",
            None,
            None,
            None,
            mock_drive,
            50,
        )

        response = self.client.post(
            self.url,
            headers={
                "X-Goog-Channel-ID": f"{self.config.pk}+{randint(1_000, 9_999)}",
                "X-Goog-Resource-State": "change",
                "X-Goog-Resource-ID": "fLt2rIVtXlXxBKz2JJaFD",
            },
        )

        assert response.status_code == 200
        mock_logger.error.assert_called_once_with("File 1 in wrong folder.")
        document = PatientDocument.objects.filter(patient=self.patient)
        assert not document.exists()

    @patch.object(GoogleDriveFile, "parent", new_callable=PropertyMock)
    @patch(MOCK_UTILS + "LOGGER")
    @patch(MOCK_ROOT + "build")
    @patch.object(Credentials, "from_service_account_info")
    def test_validate_org_slade_code(
        self, mock_credz, mock_drive, mock_logger, mock_parent
    ):
        """Test validating the org's slade code."""
        mock_credz.return_value = MagicMock()
        mock_changes = mock_drive.return_value.changes.return_value
        mock_changes.list.return_value.execute.return_value = {
            "newStartPageToken": 89,
            "changes": [
                {
                    "file": {
                        "id": "234324",
                        "mimeType": "application/pdf",
                    }
                }
            ],
        }
        mock_files = mock_drive.return_value.files.return_value
        mock_files.get.return_value.execute.return_value = {
            "mimeType": "application/pdf",
            "size": "200",
            "name": "1",
            "id": "fLt2rIVtXlXxBKz2JJaFD",
            "createdTime": "123",
            "modifiedTime": "23",
            "md5Checksum": "42",
            "parents": ["ppp"],
        }
        mock_files.list.return_value.execute.return_value = {
            "files": [
                {"name": "Processed", "id": "324234"},
                {"name": "Existing", "id": "324235"},
                {"name": "Failed", "id": "324236"},
            ]
        }
        mock_parent.return_value = FakeFolder(
            "Pending",
            0,
            "application/vnd.google-apps.folder",
            None,
            None,
            None,
            mock_drive,
            666,
        )

        response = self.client.post(
            self.url,
            headers={
                "X-Goog-Channel-ID": f"{self.config.pk}+{randint(1_000, 9_999)}",
                "X-Goog-Resource-State": "change",
                "X-Goog-Resource-ID": "fLt2rIVtXlXxBKz2JJaFD",
            },
        )

        assert response.status_code == 200
        mock_logger.error.assert_called_once_with(
            "Unknown organisation with slade code 666."
        )
        document = PatientDocument.objects.filter(patient=self.patient)
        assert not document.exists()

    @patch.object(GoogleDriveFile, "parent", new_callable=PropertyMock)
    @patch(MOCK_UTILS + "LOGGER")
    @patch(MOCK_ROOT + "build")
    @patch.object(Credentials, "from_service_account_info")
    def test_validate_post_processing_folders_exist(
        self, mock_credz, mock_drive, mock_logger, mock_parent
    ):
        """Test validating the post processing folders exist."""
        mock_credz.return_value = MagicMock()
        mock_changes = mock_drive.return_value.changes.return_value
        mock_changes.list.return_value.execute.return_value = {
            "newStartPageToken": 89,
            "changes": [
                {
                    "file": {
                        "id": "234324",
                        "mimeType": "application/pdf",
                    }
                }
            ],
        }
        mock_files = mock_drive.return_value.files.return_value
        mock_files.get.return_value.execute.return_value = {
            "mimeType": "application/pdf",
            "size": "200",
            "name": "1",
            "id": "fLt2rIVtXlXxBKz2JJaFD",
            "createdTime": "123",
            "modifiedTime": "23",
            "md5Checksum": "42",
            "parents": ["ppp"],
        }
        mock_files.list.return_value.execute.return_value = {
            "files": [
                {"name": "Existing", "id": "324235"},
                {"name": "Failed", "id": "324236"},
            ]
        }
        mock_parent.return_value = FakeFolder(
            "Pending",
            0,
            "application/vnd.google-apps.folder",
            None,
            None,
            None,
            mock_drive,
            50,
        )

        response = self.client.post(
            self.url,
            headers={
                "X-Goog-Channel-ID": f"{self.config.pk}+{randint(1_000, 9_999)}",
                "X-Goog-Resource-State": "change",
                "X-Goog-Resource-ID": "fLt2rIVtXlXxBKz2JJaFD",
            },
        )

        assert response.status_code == 200
        mock_logger.error.assert_called_once_with(
            "Post processing folders don't exist."
        )
        document = PatientDocument.objects.filter(patient=self.patient)
        assert not document.exists()

    @patch.object(GoogleDriveFile, "parent", new_callable=PropertyMock)
    @patch(MOCK_UTILS + "LOGGER")
    @patch(MOCK_ROOT + "build")
    @patch.object(Credentials, "from_service_account_info")
    def test_validate_document_already_exists(
        self, mock_credz, mock_drive, mock_logger, mock_parent
    ):
        """Test validating already existing documents."""
        baker.make(
            PatientDocument,
            patient=self.patient,
            file_hash="42",
            data=InMemoryUploadedFile(
                io.BytesIO(b""),
                None,
                "document_no",
                "application/pdf",
                0,
                None,
                None,
            ),
        )
        mock_credz.return_value = MagicMock()
        mock_changes = mock_drive.return_value.changes.return_value
        mock_changes.list.return_value.execute.return_value = {
            "newStartPageToken": 89,
            "changes": [
                {
                    "file": {
                        "id": "234324",
                        "mimeType": "application/pdf",
                    }
                }
            ],
        }
        mock_files = mock_drive.return_value.files.return_value
        mock_files.get.return_value.execute.return_value = {
            "mimeType": "application/pdf",
            "size": "200",
            "name": "1",
            "id": "fLt2rIVtXlXxBKz2JJaFD",
            "createdTime": "123",
            "modifiedTime": "23",
            "md5Checksum": "42",
            "parents": ["ppp"],
        }
        mock_files.list.return_value.execute.return_value = {
            "files": [
                {"name": "Processed", "id": "324234"},
                {"name": "Existing", "id": "324235"},
                {"name": "Failed", "id": "324236"},
            ]
        }
        mock_parent.return_value = FakeFolder(
            "Pending",
            0,
            "application/vnd.google-apps.folder",
            None,
            None,
            None,
            mock_drive,
            50,
        )

        response = self.client.post(
            self.url,
            headers={
                "X-Goog-Channel-ID": f"{self.config.pk}+{randint(1_000, 9_999)}",
                "X-Goog-Resource-State": "change",
                "X-Goog-Resource-ID": "fLt2rIVtXlXxBKz2JJaFD",
            },
        )

        assert response.status_code == 200
        mock_logger.warning.assert_called_once_with("Document # 1 already exists.")

    @patch(MOCK_ROOT + "download_patient_record")
    @patch(MOCK_ROOT + "build")
    @patch.object(Credentials, "from_service_account_info")
    def test_ignoring_folder_notifications(self, mock_credz, mock_drive, mock_download):
        """Test ignoring folder notifications."""
        mock_credz.return_value = MagicMock()
        mock_changes = mock_drive.return_value.changes.return_value
        mock_changes.list.return_value.execute.return_value = {
            "newStartPageToken": 89,
            "changes": [
                {
                    "file": {
                        "id": "234324",
                        "mimeType": "application/vnd.google-apps.folder",
                    }
                }
            ],
        }
        mock_files = mock_drive.return_value.files.return_value
        mock_files.get.return_value.execute.return_value = {
            "mimeType": "application/vnd.google-apps.folder",
            "size": "200",
            "name": "1",
            "id": "fLt2rIVtXlXxBKz2JJaFD",
            "createdTime": "123",
            "modifiedTime": "23",
            "md5Checksum": "42",
            "parents": ["ppp"],
        }

        response = self.client.post(
            self.url,
            headers={
                "X-Goog-Channel-ID": f"{self.config.pk}+{randint(1_000, 9_999)}",
                "X-Goog-Resource-State": "change",
                "X-Goog-Resource-ID": "fLt2rIVtXlXxBKz2JJaFD",
            },
        )

        assert response.status_code == 200
        mock_download.assert_not_called()

    @patch(MOCK_ROOT + "build")
    @patch.object(Credentials, "from_service_account_info")
    def test_open_google_drive_channels(self, mock_credz, mock_drive):
        """Test opening a Google Drive channel."""
        mock_changes = mock_drive.return_value.changes.return_value
        mock_changes.getStartPageToken.return_value.execute.return_value = {
            "startPageToken": "56",
        }
        open_google_drive_channels()
        mock_drive.return_value.changes.return_value.watch.assert_called_once()

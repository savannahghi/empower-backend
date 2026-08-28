"""Google Drive Integration."""
import io
import uuid
from datetime import timedelta
from functools import cached_property
from random import randint
from typing import Optional, Self

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import Resource, build
from googleapiclient.http import MediaIoBaseDownload
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK
from rest_framework.views import APIView

from sil_advantage.common.tasks import BaseTaskWithRetry
from sil_advantage.config import celery_app
from sil_advantage.integrations.files.base import AbstractFile
from sil_advantage.integrations.files.utils import download_patient_record
from sil_advantage.integrations.models import IntegrationConfig


class GoogleDriveFile(AbstractFile):
    """Google Drive File."""

    @classmethod
    def new(cls, file_id: str, drive: Resource) -> Self:
        """Return an instance of `GoogleDriveFile`."""
        file = (
            drive.files()
            .get(
                fileId=file_id,
                fields="id,mimeType,size,name,md5Checksum,parents,createdTime,modifiedTime",
            )
            .execute()
        )

        parents = file.get("parents", [])
        if len(parents) > 0:
            parent = parents[0]
        else:
            parent = None

        return cls(
            file["name"],
            int(file.get("size", 0)),
            file["mimeType"],
            file["createdTime"],
            file["modifiedTime"],
            {
                "id": file["id"],
                "md5Checksum": file.get("md5Checksum", None),
                "parent": parent,
            },
            drive,
        )

    @property
    def hash(self) -> str:
        """Get the file hash."""
        assert self.metadata is not None
        return self.metadata["md5Checksum"]

    def read(self) -> bytes:
        """Read the file content from Google Drive."""
        assert self.metadata is not None
        request = self.adapter.files().get_media(fileId=self.metadata["id"])
        fd = io.BytesIO()
        downloader = MediaIoBaseDownload(
            fd,
            request,
            chunksize=settings.FILE_UPLOAD_CHUNK_SIZE,
        )

        done = False
        while done is False:
            _, done = downloader.next_chunk()

        return fd.getvalue()

    def move(self, dest: str) -> None:
        """Move the file to destination `dest`."""
        assert self.metadata is not None
        drive: Resource = self.adapter
        drive.files().update(
            fileId=self.metadata["id"],
            addParents=dest,
            removeParents=self.metadata["parent"],
        ).execute()
        self.metadata["parent"] = dest

    @cached_property
    def parent(self) -> Optional["GoogleDriveFile"]:
        """Get the parent folder."""
        assert self.metadata is not None
        folder_id = self.metadata["parent"]
        if folder_id is None:
            return None

        return GoogleDriveFile.new(folder_id, self.adapter)


def get_google_drive_client(integration_config: IntegrationConfig) -> Resource:
    """Return a Google Drive client."""
    credentials = (
        Credentials
        .from_service_account_info(integration_config.config)
        .with_scopes(["https://www.googleapis.com/auth/drive"])
    )  # fmt: skip
    return build("drive", "v3", credentials=credentials)


""" Tasks """


@celery_app.task(base=BaseTaskWithRetry)
def process_google_drive_notification(config_id: uuid.UUID) -> None:
    """Process Google Drive notification."""
    integration_config = IntegrationConfig.objects.get(pk=config_id)
    drive = get_google_drive_client(integration_config)
    change_list = (
        drive.changes()
        .list(
            pageToken=integration_config.metadata["pageToken"],
            includeRemoved=False,
            pageSize=1_000,
        )
        .execute()
    )
    for change in change_list["changes"]:
        file = change["file"]
        key = f"google_drive_file_lock_{file['id']}"
        if (
            file["mimeType"] != "application/vnd.google-apps.folder"
            and cache.get(key, None) is None
        ):
            cache.set(key, True, timeout=7_200)  # 2 hours
            resource = GoogleDriveFile.new(file["id"], drive)
            downloaded = download_patient_record(resource)
            if not downloaded:
                cache.delete(key)
    integration_config.metadata["pageToken"] = change_list["newStartPageToken"]
    integration_config.save(update_fields=["metadata"])


@celery_app.task(base=BaseTaskWithRetry)
def open_google_drive_channels() -> None:
    """Open Google Drive channels."""
    configs = IntegrationConfig.objects.filter(
        system="GOOGLE_DRIVE",
        active=True,
        config__isnull=False,
    )
    for config in configs:
        drive = get_google_drive_client(config)
        token = drive.changes().getStartPageToken().execute()["startPageToken"]
        expiry = int((timezone.now() + timedelta(days=1)).timestamp() * 1000)
        random_offset = randint(1_000, 9_999)
        body = {
            "kind": "api#channel",
            "id": f"{config.pk}+{random_offset}",
            "type": "web_hook",
            "address": f"{settings.API_HOST}/api/integrations/google-drive/",
            "expiration": expiry,
        }
        drive.changes().watch(pageToken=token, body=body).execute()
        config.metadata["pageToken"] = token
        config.save(update_fields=["metadata"])


""" Endpoints """


class GoogleDriveWebhook(APIView):
    """Google Drive Change Notifications Webhook."""

    permission_classes = (AllowAny,)

    def post(self, request: Request) -> Response:
        """Process Google Drive change notifications."""
        headers = request.headers
        channel_id = headers["X-Goog-Channel-ID"].split("+")[0]
        config = IntegrationConfig.objects.filter(
            pk=channel_id,
            system="GOOGLE_DRIVE",
            active=True,
        ).only("id")

        state = headers["X-Goog-Resource-State"]
        if state not in ("change", "sync") or not config.exists():
            # 1: Ignore changes we don't care about
            #    like: remove, trash
            # 2: For security, only accept channel IDs we recognize
            return Response(status=HTTP_200_OK)

        process_google_drive_notification.apply_async(
            queue=settings.CELERY_DEFAULT_QUEUE,
            priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
            args=(config.latest("updated").id,),
        )

        return Response(status=HTTP_200_OK)

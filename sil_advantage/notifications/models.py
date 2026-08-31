"""Notifications models."""
import logging
import os
from typing import Any, Optional

import aiofiles
from asgiref.sync import async_to_sync
from django.db import models
from django.utils.functional import cached_property
from nio.api import RoomVisibility
from sil_cacheable.orm import CacheableManager

from sil_advantage.common.models import (
    AbstractBase,
    Organisation,
    OrgUnitIdsMixin,
    Person,
    UserProfile,
)
from sil_advantage.notifications import (
    GROUP_ROLES,
    USSD_CODE_TYPE,
    USSD_GATEWAYS,
)
from sil_advantage.notifications.matrix import get_matrix_client

LOGGER = logging.getLogger(__name__)


class Group(AbstractBase):
    """A notifications group."""

    role = models.CharField(max_length=64, choices=GROUP_ROLES)
    description = models.TextField(null=True, blank=True)

    matrix_room_id = models.CharField(
        max_length=256,
        null=True,
        blank=True,
    )

    objects: models.Manager["Group"] = CacheableManager()
    _related_serialized_models = "notifications_groupmember"

    members: models.QuerySet["GroupMember"]

    @cached_property
    def email_recipients(self) -> list[str]:
        """Return the email addresses of group members."""
        return [
            member.email_address
            for member in self.members.all().order_by("created")
            if member.email_address is not None
        ]

    @async_to_sync
    async def create_on_matrix(self) -> None:
        """Create this group on Matrix."""
        if self.matrix_room_id is not None:
            return

        client = await get_matrix_client()
        role = " ".join(self.role.split("_")).title()
        org = await Organisation.objects.aget(
            pk=self.organisation_id,
        )
        response = await client.room_create(
            name=f"{org.short_name} - {role}",
            visibility=RoomVisibility.private,
            topic=self.role,
            is_direct=False,
            federate=False,
        )
        room_id = (await response.transport_response.json())["room_id"]
        self.matrix_room_id = room_id
        await client.close()

    @async_to_sync
    async def send_message_to_matrix_room(self, body: str) -> None:
        """Send message to the matrix room."""
        if self.matrix_room_id is None:
            LOGGER.warning("Message group not created on Matrix")
            return

        payload = {
            "body": body,
            "msgtype": "m.text",
            "format": "org.matrix.custom.html",
            "formatted_body": body,
        }

        client = await get_matrix_client()
        await client.room_send(
            self.matrix_room_id,
            "m.room.message",
            content=payload,
        )
        await client.close()

    @async_to_sync
    async def send_file_to_matrix_room(
        self, filepath: str, mime_type: str, filename: str
    ) -> None:
        """Send file to the matrix room."""
        if self.matrix_room_id is None:
            LOGGER.warning("Message group not created on Matrix")
            return

        client = await get_matrix_client()
        filesize = os.stat(filepath).st_size
        async with aiofiles.open(filepath, "rb") as fd:
            upload_resp, _ = await client.upload(
                fd,
                content_type=mime_type,
                filename=filename,
                filesize=filesize,
            )

        payload = {
            "body": filename,
            "info": {
                "mimetype": mime_type,
                "size": filesize,
            },
            "msgtype": "m.file",
            "url": upload_resp.content_uri,
        }
        await client.room_send(
            self.matrix_room_id,
            message_type="m.room.message",
            content=payload,
        )
        await client.close()

    @async_to_sync
    async def invite_member(self, matrix_user_id: str) -> None:
        """Invite a member to a Matrix room."""
        client = await get_matrix_client()
        await client.room_invite(self.matrix_room_id, matrix_user_id)
        await client.close()

    @async_to_sync
    async def remove_member(self, matrix_user_id: str) -> None:
        """Kick a member from a Matrix room."""
        client = await get_matrix_client()
        await client.room_kick(self.matrix_room_id, matrix_user_id)
        await client.close()

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save a group."""
        if self.matrix_room_id is None:
            self.create_on_matrix()

        super().save(*args, **kwargs)

    class Meta(AbstractBase.Meta):
        """Model options."""

        unique_together = [
            (
                "role",
                "organisation",
            ),
        ]


class GroupMember(AbstractBase):
    """Notifications recipient."""

    person = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="group_members",
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.PROTECT,
        related_name="members",
    )

    objects: models.Manager["Group"] = CacheableManager()

    @cached_property
    def profile(self) -> Optional[UserProfile]:
        """Return the recipient's profile if available."""
        return (
            UserProfile.objects.filter(person=self.person)
            .select_related("user")
            .first()
        )

    @cached_property
    def email_address(self) -> Optional[str]:
        """Return the recipient's email address."""
        email = None
        profile = self.profile
        if profile is not None:
            email = profile.user.email
        else:
            email = self.person.email
        return email

    @async_to_sync
    async def join_matrix_room(self) -> None:
        """Join a Matrix room."""
        person = await Person.objects.aget(pk=self.person_id)
        profile = await (
            UserProfile.objects.filter(person=person).select_related("user").afirst()
        )
        assert profile is not None and profile.user.matrix_user_id is not None
        client = await get_matrix_client(profile.user.guid)
        group = await Group.objects.aget(pk=self.group_id)
        await client.join(group.matrix_room_id)
        await client.close()

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Add a member to Matrix room."""
        profile = self.profile
        if self._state.adding and profile is not None:
            assert profile.user.matrix_user_id is not None
            self.group.invite_member(profile.user.matrix_user_id)
            self.join_matrix_room()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> None:
        """Remove their membership on Matrix."""
        profile = self.profile
        if profile is not None:
            assert profile.user.matrix_user_id is not None
            self.group.remove_member(profile.user.matrix_user_id)
        super().delete(*args, **kwargs)


class USSDCode(OrgUnitIdsMixin, AbstractBase):  # type: ignore
    """USSD Service Codes."""

    ussd_code = models.CharField(max_length=255, unique=True)
    gateway = models.CharField(max_length=50, choices=USSD_GATEWAYS)
    type = models.CharField(max_length=50, choices=USSD_CODE_TYPE)

    def __str__(self) -> str:
        """String representation of ussdcode."""
        return self.ussd_code

    @classmethod
    def get_org_ussd_codes(
        cls,
        organisation: Organisation,
    ) -> models.QuerySet["USSDCode"]:
        """Return an organisation's USSD codes."""
        return cls.objects.filter(
            organisation=organisation,
        )

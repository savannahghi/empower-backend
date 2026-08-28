"""Test notifications models."""
import tempfile
from unittest.mock import MagicMock, patch

from django.test import override_settings
from model_bakery import baker
from nio import AsyncClient

from sil_advantage.notifications.models import Group, GroupMember, USSDCode
from tests.common.test_common_views import LoggedInMixin
from tests.common.utility import AsyncMagicMock, PicklableMagicMock

MOCK_ROOT = "sil_advantage.notifications.models."


@override_settings(MATRIX_SECRET="a-secret")
class TestMessageGroups(LoggedInMixin):
    """Test message groups."""

    @patch.object(AsyncClient, "room_create", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "login", new_callable=AsyncMagicMock)
    def setUp(self, mock_matrix_login, mock_create_matrix_room) -> None:
        """Set up test environment."""
        super().setUp()
        mock_create_matrix_room.transport_response.json.return_value = {
            "room_id": "!asdfasdf:example.com",
        }

        self.org = self.global_organisation
        self.group = baker.make(
            Group,
            role="DAILY_DIGEST",
            matrix_room_id="!asdfasdf:example.com",
            organisation=self.org,
        )
        self.group.create_on_matrix()

    @patch.object(AsyncClient, "room_send", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "login", new_callable=AsyncMagicMock)
    def test_send_formatted_message_on_matrix(
        self,
        mock_matrix_login,
        mock_matrix_send_to_room,
    ):
        """Test sending a formatted message on Matrix."""
        self.group.send_message_to_matrix_room(
            "<b>Hey, I'm Jane</b>",
        )

        mock_matrix_send_to_room.assert_called_once_with(
            "!asdfasdf:example.com",
            "m.room.message",
            content={
                "body": "<b>Hey, I'm Jane</b>",
                "msgtype": "m.text",
                "format": "org.matrix.custom.html",
                "formatted_body": "<b>Hey, I'm Jane</b>",
            },
        )

    @patch.object(AsyncClient, "room_send", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "login", new_callable=AsyncMagicMock)
    def test_send_unformatted_message_on_matrix(
        self,
        mock_matrix_login,
        mock_matrix_send_to_room,
    ):
        """Test sending an unformatted message on Matrix."""
        self.group.send_message_to_matrix_room("Heyoo!")

        mock_matrix_send_to_room.assert_called_once_with(
            "!asdfasdf:example.com",
            "m.room.message",
            content={
                "body": "Heyoo!",
                "msgtype": "m.text",
                "format": "org.matrix.custom.html",
                "formatted_body": "Heyoo!",
            },
        )

    @patch(MOCK_ROOT + "LOGGER")
    def test_send_message_no_matrix_room_id(self, mock_logger):
        """Test sending a message with no `matrix_room_id`."""
        self.group.matrix_room_id = None

        self.group.send_message_to_matrix_room("Heyoo!")

        mock_logger.warning.assert_called_once_with(
            "Message group not created on Matrix",
        )

    @patch.object(AsyncClient, "room_send", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "upload", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "login", new_callable=AsyncMagicMock)
    def test_send_file_to_matrix(
        self,
        mock_matrix_login,
        mock_matrix_upload,
        mock_matrix_send_to_room,
    ):
        """Test sending a file to Matrix."""
        upload_resp = MagicMock()
        upload_resp.content_uri = "mxc://localhost/haunting"
        mock_matrix_upload.return_value = upload_resp, None

        with tempfile.NamedTemporaryFile() as fd:
            self.group.send_file_to_matrix_room(
                fd.name,
                "application/pdf",
                "You're Haunting Me",
            )

        mock_matrix_send_to_room.assert_called_once_with(
            "!asdfasdf:example.com",
            message_type="m.room.message",
            content={
                "body": "You're Haunting Me",
                "info": {"mimetype": "application/pdf", "size": 0},
                "msgtype": "m.file",
                "url": "mxc://localhost/haunting",
            },
        )

    @patch(MOCK_ROOT + "LOGGER")
    def test_send_file_no_matrix_room_id(self, mock_logger):
        """Test sending a file with no `matrix_room_id`."""
        self.group.matrix_room_id = None

        with tempfile.NamedTemporaryFile() as fd:
            self.group.send_file_to_matrix_room(
                fd.name,
                "application/pdf",
                "The Promise",
            )

        mock_logger.warning.assert_called_once_with(
            "Message group not created on Matrix",
        )

    @patch.object(AsyncClient, "room_kick", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "join", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "room_invite", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "login", new_callable=AsyncMagicMock)
    @patch(
        "sil_advantage.notifications.matrix.requests",
        new_callable=PicklableMagicMock,
    )
    def test_invite_and_kick_member_on_matrix(
        self,
        mock_matrix_requests,
        mock_matrix_login,
        mock_matrix_room_invite,
        mock_matrix_join,
        mock_matrix_room_kick,
    ):
        """Test inviting & kicking member on Matrix."""
        matrix_uid = "@2bdf4e17-cb39-4626-a29d-a80040d67857:slade360edi.com"
        mock_matrix_requests.post.return_value.json.return_value = {
            "user_id": matrix_uid,
            "access_token": "my-access-token",
            "home_server": "slade360edi.com",
            "device_id": "GVROMSUCDE",
            "well_known": {
                "m.homeserver": {
                    "base_url": "https://matrix.slade360.uat.slade360edi.com/"
                }
            },
            "_cache_key": "2d0340b3bfedb72dfcb845e8d32b31b7",
        }

        member = baker.make(
            GroupMember,
            group=self.group,
            person=self.global_person,
            organisation=self.org,
        )

        mock_matrix_room_invite.assert_called_once_with(
            "!asdfasdf:example.com",
            "@2bdf4e17-cb39-4626-a29d-a80040d67857:slade360edi.com",
        )
        mock_matrix_join.assert_called_once_with("!asdfasdf:example.com")

        member.delete()

    @patch.object(AsyncClient, "room_kick", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "room_invite", new_callable=AsyncMagicMock)
    @patch.object(AsyncClient, "login", new_callable=AsyncMagicMock)
    def test_delete_member_with_no_profile(
        self, mock_matrix_login, mock_matrix_room_invite, mock_matrix_room_kick
    ):
        """Test deleting a member with no profile."""
        member = baker.make(
            GroupMember,
            group=self.group,
            organisation=self.org,
        )

        member.delete()

        mock_matrix_room_kick.assert_not_called()

    def test_create_ussd_code(self):
        """Test creating a USSD code."""
        ussd_code = baker.make(
            USSDCode,
            ussd_code="*393#",
            gateway="SAFARICOM",
            type="PREPAID",
            organisation=self.org,
        )
        assert ussd_code.ussd_code == "*393#"
        assert ussd_code.gateway == "SAFARICOM"
        assert ussd_code.type == "PREPAID"

    def test_unicode_representation(self):
        """Test string representation of USSDCode."""
        ussd_code = baker.make(USSDCode, ussd_code="*393#", organisation=self.org)
        assert str(ussd_code) == "*393#"

    def test_get_org_ussd_codes(self):
        """Test retrieving an organisation's USSD codes."""
        ussd_code1 = baker.make(
            USSDCode,
            ussd_code="*393#",
            gateway="SAFARICOM",
            type="PREPAID",
            organisation=self.org,
        )
        ussd_code2 = baker.make(
            USSDCode,
            ussd_code="*393*5113#",
            gateway="SAFARICOM",
            type="POSTPAID",
            organisation=self.org,
        )

        ussd_codes = USSDCode.get_org_ussd_codes(self.org)
        assert ussd_codes.count() == 2
        assert ussd_code1 in ussd_codes
        assert ussd_code2 in ussd_codes

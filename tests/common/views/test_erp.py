"""Test ERP proxy view."""
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from tests.common.test_common_views import LoggedInMixin

MOCK_ROOT = "sil_advantage.common.views.erp."


@override_settings(
    ERP_API_CONFIG={
        "api_host": "erp.slade360.co.ke/api",
        "api_scheme": "https",
        "oauth_client_id": "i-am-client-ID",
        "oauth_client_secret": "neno-siri",
        "user_email": "advantage_test@slade360.co.ke",
        "user_password": "Some=SecurePassword!",
        "token_url": "https://authserver.advantage.slade360.co.ke/",
    }
)
class ERPProxyViewTestCase(LoggedInMixin):
    """Test the ERP Proxy View."""

    url = reverse("erp", kwargs={"resource": "sales/salesorder/"})
    workstation = "4df08a69-3b66-4a77-bceb-6b4f876da08c"
    origin = "https://advantage.slade360.com"
    variant = "default"
    referer = "http://127.0.0.1/"

    @patch(MOCK_ROOT + "make_request")
    def test_get_call(self, mock_make_request):
        """Test a GET call to the ERP."""
        mock_make_request.return_value = {}, 200

        self.client._credentials["HTTP_X_WORKSTATION"] = self.workstation
        self.client._credentials["HTTP_ORIGIN"] = self.origin
        self.client._credentials["HTTP_X_VARIANT"] = self.variant
        self.client._credentials["HTTP_REFERER"] = self.referer
        self.client.get(self.url)

        mock_make_request.assert_called_once()
        call_args = mock_make_request.call_args
        assert call_args.args[:2] == (
            "GET",
            "https://erp.slade360.co.ke/api/sales/salesorder/",
        )
        assert call_args.kwargs == {
            "extra_headers": {
                "X-Workstation": "4df08a69-3b66-4a77-bceb-6b4f876da08c",
                "HTTP_ORIGIN": "https://advantage.slade360.com",
                "X-Variant": "default",
                "Referer": "http://127.0.0.1/",
            }
        }

    @patch(MOCK_ROOT + "make_request")
    def test_post_call(self, mock_make_request):
        """Test a POST call to the ERP."""
        mock_make_request.return_value = {}, 200

        self.client.post(self.url)

        mock_make_request.assert_called_once()
        call_args = mock_make_request.call_args
        assert call_args.args[:2] == (
            "POST",
            "https://erp.slade360.co.ke/api/sales/salesorder/",
        )
        assert call_args.kwargs == {
            "extra_headers": {
                "X-Workstation": None,
                "HTTP_ORIGIN": None,
                "X-Variant": None,
                "Referer": None,
            },
            "payload": {},
        }

    @patch(MOCK_ROOT + "make_request")
    def test_put_call(self, mock_make_request):
        """Test a PUT call to the ERP."""
        mock_make_request.return_value = {}, 200

        self.client._credentials["HTTP_X_WORKSTATION"] = self.workstation
        self.client._credentials["HTTP_ORIGIN"] = self.origin
        self.client._credentials["HTTP_X_VARIANT"] = self.variant
        self.client._credentials["HTTP_REFERER"] = self.referer
        self.client.put(self.url)

        mock_make_request.assert_called_once()
        call_args = mock_make_request.call_args
        assert call_args.args[:2] == (
            "PUT",
            "https://erp.slade360.co.ke/api/sales/salesorder/",
        )
        assert call_args.kwargs == {
            "extra_headers": {
                "X-Workstation": "4df08a69-3b66-4a77-bceb-6b4f876da08c",
                "HTTP_ORIGIN": "https://advantage.slade360.com",
                "X-Variant": "default",
                "Referer": "http://127.0.0.1/",
            },
            "payload": {},
        }

    @patch(MOCK_ROOT + "make_request")
    def test_patch_call(self, mock_make_request):
        """Test a PATCH call."""
        mock_make_request.return_value = {}, 200

        self.client._credentials["HTTP_X_WORKSTATION"] = self.workstation
        self.client._credentials["HTTP_ORIGIN"] = self.origin
        self.client._credentials["HTTP_X_VARIANT"] = self.variant
        self.client._credentials["HTTP_REFERER"] = self.referer
        self.client.patch(self.url)

        mock_make_request.assert_called_once()
        call_args = mock_make_request.call_args
        assert call_args.args[:2] == (
            "PATCH",
            "https://erp.slade360.co.ke/api/sales/salesorder/",
        )
        assert call_args.kwargs == {
            "extra_headers": {
                "X-Workstation": "4df08a69-3b66-4a77-bceb-6b4f876da08c",
                "HTTP_ORIGIN": "https://advantage.slade360.com",
                "X-Variant": "default",
                "Referer": "http://127.0.0.1/",
            },
            "payload": {},
        }

    @patch(MOCK_ROOT + "make_request")
    def test_delete_call(self, mock_make_request):
        """Test a DELETE call to the ERP."""
        mock_make_request.return_value = {}, 200

        self.client._credentials["HTTP_X_WORKSTATION"] = self.workstation
        self.client._credentials["HTTP_ORIGIN"] = self.origin
        self.client._credentials["HTTP_X_VARIANT"] = self.variant
        self.client._credentials["HTTP_REFERER"] = self.referer
        self.client.delete(self.url)

        mock_make_request.assert_called_once()
        call_args = mock_make_request.call_args
        assert call_args.args[:2] == (
            "DELETE",
            "https://erp.slade360.co.ke/api/sales/salesorder/",
        )
        assert call_args.kwargs == {
            "extra_headers": {
                "X-Workstation": "4df08a69-3b66-4a77-bceb-6b4f876da08c",
                "HTTP_ORIGIN": "https://advantage.slade360.com",
                "X-Variant": "default",
                "Referer": "http://127.0.0.1/",
            }
        }

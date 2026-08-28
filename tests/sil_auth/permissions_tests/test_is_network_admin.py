"""Tests or network admin."""
from django.test.utils import override_settings
from django.urls import reverse

from sil_advantage.permissions import perms as perms
from tests.common.test_common_views import LoggedInMixin


@override_settings(ROOT_URLCONF="tests.sil_auth.permissions_tests.urls")
class TestDocumentPermission(LoggedInMixin):
    """Test case for documment permission."""

    def test_a_user_who_is_an_admin(self):
        """Test a user without admin permissions."""
        response = self.client.get(reverse("test_list"))
        assert response.status_code == 403
        assert (
            response.data["detail"]
            == "Permission denied: You must be a network administrator"
            " to perform this action"
        )

    def test_a_user_with_an_active_org_gets_200(self):
        """Test user has admin permissions."""
        self.assign_permission([perms.CROSS_NETWORK_ADMIN[0]])
        response = self.client.get(reverse("test_list"))
        assert response.status_code == 200

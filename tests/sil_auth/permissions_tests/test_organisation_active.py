"""Test for organisation."""
from django.core.cache import cache
from django.urls import reverse

from tests.common.test_common_views import LoggedInMixin


class TestDocumentPermission(LoggedInMixin):
    """Test case for organisation status."""

    def test_a_user_with_inactive_org_gets_403(self):
        """Test user with an inactive organisation."""
        org = self.user.organisation
        cache.delete(self.user.profile._cache_key)
        org.active = False
        org.note = "Tume-toa hii"
        org.save()
        response = self.client.get(reverse("organisation-list"))
        assert response.status_code == 403
        assert response.data == {
            "detail": "You do not have permission to perform this action."
        }

    def test_a_user_with_an_active_org_gets_200(self):
        """Test user with an active organisation."""
        response = self.client.get(reverse("organisation-list"))
        assert response.status_code == 200
